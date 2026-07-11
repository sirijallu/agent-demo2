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

MODEL = "claude-opus-4-8"


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
   visa requirements, weather to expect).

Keep the response well-organized with headers, and keep it practical rather
than exhaustive."""


def main() -> None:
    api_key = load_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    trip = collect_trip_details()
    prompt = build_prompt(trip)

    print("\nThinking through your options...\n")

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            tools=[
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": 5,
                }
            ],
            system=(
                "You are an experienced, friendly travel agent. Give concrete, "
                "practical recommendations tailored to the traveler's stated "
                "budget, timing, and interests. Be concise but specific."
            ),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            print()
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
