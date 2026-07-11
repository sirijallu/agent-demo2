"""Vercel serverless function powering the website's floating travel-agent widget.

Mirrors the prompt, model, and tool config used by the terminal CLI in
../agent-demo2.py so the web experience matches the terminal experience.
"""

import os

from flask import Flask, Response, request
import anthropic

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = (
    "You are an experienced, friendly travel agent. Give concrete, "
    "practical recommendations tailored to the traveler's stated "
    "budget, timing, and interests. Be concise but specific."
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
   visa requirements, weather to expect).

Keep the response well-organized with headers, and keep it practical rather
than exhaustive."""


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
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except anthropic.AuthenticationError:
            yield "\n[error] Invalid API key configured on the server."
        except anthropic.RateLimitError:
            yield "\n[error] Rate limited by the API — please wait a moment and try again."
        except anthropic.APIStatusError as e:
            yield f"\n[error] API error ({e.status_code}): {e.message}"
        except anthropic.APIConnectionError:
            yield "\n[error] Couldn't reach the Anthropic API — check your network connection."

    return Response(generate(), mimetype="text/plain")
