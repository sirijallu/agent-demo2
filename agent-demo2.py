#!/usr/bin/env python3
"""Travel Agent CLI powered by Claude.

Collects a traveler's preferences interactively, then asks Claude to
recommend vacation destinations, a rough itinerary, and flight options.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import anthropic

sys.path.append(str(Path(__file__).resolve().parent / "api"))
from _rag import POLICY_TOOL, retrieve  # noqa: E402

MODEL = "claude-opus-4-8"
MAX_TOOL_TURNS = 4


def load_api_key() -> str:
    config_path = Path(__file__).resolve().parent / "config.env"
    load_dotenv(dotenv_path=config_path)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "your-api-key-here":
        print(
            f"No Anthropic API key found. Edit {config_path} and set "
            "ANTHROPIC_API_KEY to your key from https://console.anthropic.com/settings/keys",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def collect_trip_details() -> dict:
    print("=" * 60)
    print("  Claude Travel Agent — let's plan your next vacation")
    print("=" * 60)

    return {
        "origin": ask("Departure city"),
        "budget": ask("Total budget (e.g. $2000 per person, flexible)"),
        "duration": ask("Trip length (e.g. 7 days)"),
        "timing": ask("When are you thinking of traveling? (dates or season)"),
        "travelers": ask("Who's going? (e.g. 2 adults, solo, family with kids)"),
        "interests": ask(
            "What kind of trip? (beach, adventure, culture, food, nightlife, "
            "nature, relaxation, family-friendly...)"
        ),
        "climate": ask("Preferred climate (warm, cold, mild, no preference)", "no preference"),
        "notes": ask("Anything else? (visa constraints, must-avoid, accessibility needs)", "none"),
    }


def build_prompt(trip: dict) -> str:
    return f"""Plan a vacation for me based on these preferences:

- Departure city: {trip['origin']}
- Budget: {trip['budget']}
- Trip length: {trip['duration']}
- Timing: {trip['timing']}
- Travelers: {trip['travelers']}
- Interests / trip vibe: {trip['interests']}
- Preferred climate: {trip['climate']}
- Other notes: {trip['notes']}

Please:
1. Recommend 3 destinations that fit these preferences, with a short reason each.
2. For your top pick, sketch a rough day-by-day itinerary highlighting must-do
   activities that match my interests.
3. Suggest flight options from my departure city for the top pick — realistic
   airlines/routes (direct vs. connecting) and an approximate price range.
   Use web search for current, realistic information where useful, and note
   that exact prices vary and should be confirmed on a booking site.
4. Flag anything relevant to my budget, timing, or notes (e.g. peak season,
   visa requirements, weather to expect). If my notes touch on cancellation,
   baggage, or insurance, check Wanderly's policies and answer specifically.

Keep the response well-organized with headers, and keep it practical rather
than exhaustive."""


def main() -> None:
    api_key = load_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    trip = collect_trip_details()
    prompt = build_prompt(trip)

    print("\nThinking through your options...\n")

    system_prompt = (
        "You are an experienced, friendly travel agent at Wanderly. Give concrete, "
        "practical recommendations tailored to the traveler's stated budget, "
        "timing, and interests. Be concise but specific. You have access to "
        "Wanderly's policy knowledge base (cancellation & refunds, baggage, "
        "travel insurance) via the search_policies tool — consult it rather than "
        "guessing whenever policy details are relevant to the traveler's "
        "questions or plans, and fold what you find into your answer, citing "
        "the policy terms specifically."
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        for _ in range(MAX_TOOL_TURNS):
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                tools=[
                    {
                        "type": "web_search_20260209",
                        "name": "web_search",
                        "max_uses": 5,
                    },
                    POLICY_TOOL,
                ],
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                final = stream.get_final_message()

            if final.stop_reason != "tool_use":
                print()
                break

            tool_results = []
            for block in final.content:
                if block.type == "tool_use" and block.name == "search_policies":
                    print(f"\n[checking Wanderly policies: {block.input.get('query', '')}]\n", flush=True)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": retrieve(block.input.get("query", "")),
                        }
                    )
            if not tool_results:
                print()
                break

            messages.append({"role": "assistant", "content": final.content})
            messages.append({"role": "user", "content": tool_results})
    except anthropic.AuthenticationError:
        print("\nInvalid API key. Check ANTHROPIC_API_KEY in config.env.", file=sys.stderr)
        sys.exit(1)
    except anthropic.RateLimitError:
        print("\nRate limited by the API — please wait a moment and try again.", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIStatusError as e:
        print(f"\nAPI error ({e.status_code}): {e.message}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIConnectionError:
        print("\nCouldn't reach the Anthropic API — check your network connection.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
