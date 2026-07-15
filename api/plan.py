"""Vercel serverless function powering the website's floating travel-agent widget.

Mirrors the prompt, model, and tool config used by the terminal CLI in
../agent-demo2.py so the web experience matches the terminal experience.
Includes the search_policies Agentic-RAG tool over the Wanderly knowledge base.
"""

import os
import sys

from flask import Flask, Response, request
import anthropic

sys.path.append(os.path.dirname(__file__))
from _rag import POLICY_TOOL, retrieve  # noqa: E402

MODEL = "claude-opus-4-8"
MAX_TOOL_TURNS = 4

SYSTEM_PROMPT = (
    "You are an experienced, friendly travel agent at Wanderly. Give concrete, "
    "practical recommendations tailored to the traveler's stated budget, timing, "
    "and interests. Be concise but specific. You have access to Wanderly's "
    "policy knowledge base (cancellation & refunds, baggage, travel insurance) "
    "via the search_policies tool — consult it rather than guessing whenever "
    "policy details are relevant to the traveler's questions or plans, and fold "
    "what you find into your answer, citing the policy terms specifically."
)

REQUIRED_FIELDS = ["origin", "budget", "duration", "timing", "travelers", "interests"]

app = Flask(__name__)


def build_prompt(trip: dict) -> str:
    return f"""Plan a vacation for me based on these preferences:

- Departure city: {trip.get('origin', '')}
- Budget: {trip.get('budget', '')}
- Trip length: {trip.get('duration', '')}
- Timing: {trip.get('timing', '')}
- Travelers: {trip.get('travelers', '')}
- Interests / trip vibe: {trip.get('interests', '')}
- Preferred climate: {trip.get('climate') or 'no preference'}
- Other notes: {trip.get('notes') or 'none'}

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


def stream_plan(client: anthropic.Anthropic, prompt: str):
    """Agentic loop: stream text, run search_policies when Claude asks for it."""
    messages = [{"role": "user", "content": prompt}]

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
            system=SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()

        if final.stop_reason != "tool_use":
            return

        tool_results = []
        for block in final.content:
            if block.type == "tool_use" and block.name == "search_policies":
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": retrieve(block.input.get("query", "")),
                    }
                )
        if not tool_results:
            return

        messages.append({"role": "assistant", "content": final.content})
        messages.append({"role": "user", "content": tool_results})

    yield "\n\n(Stopped after reaching the policy-search limit for one request.)"


@app.route("/api/plan", methods=["POST"])
def plan():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return Response("Server is missing ANTHROPIC_API_KEY.", status=500)

    trip = request.get_json(force=True, silent=True) or {}
    missing = [f for f in REQUIRED_FIELDS if not str(trip.get(f, "")).strip()]
    if missing:
        return Response(f"Missing fields: {', '.join(missing)}", status=400)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(trip)

    def generate():
        try:
            yield from stream_plan(client, prompt)
        except anthropic.AuthenticationError:
            yield "\n[error] Invalid API key configured on the server."
        except anthropic.RateLimitError:
            yield "\n[error] Rate limited by the API — please wait a moment and try again."
        except anthropic.APIStatusError as e:
            yield f"\n[error] API error ({e.status_code}): {e.message}"
        except anthropic.APIConnectionError:
            yield "\n[error] Couldn't reach the Anthropic API — check your network connection."

    return Response(generate(), mimetype="text/plain")
