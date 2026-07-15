"""Vercel serverless function for direct policy questions.

Unlike /api/plan (which uses agentic RAG over a Voyage/Blob index), this
endpoint answers straight from the bundled policy document and needs only
ANTHROPIC_API_KEY. The knowledge base is small enough to pass in full, so it
stays reliable even if the Voyage/Blob keys aren't configured.
"""

import os
from pathlib import Path

from flask import Flask, Response, request
import anthropic

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = (
    "You are Wanderly's travel concierge. Answer the traveler's question using "
    "ONLY the policy document provided below. Quote the specific numbers, tiers, "
    "windows, and conditions that apply. If the document doesn't cover the "
    "question, say so plainly and suggest contacting the Wanderly concierge. "
    "Keep the answer concise and well-formatted with short headings or bullets "
    "where it helps."
)

app = Flask(__name__)

_policies_cache = None


def load_policies() -> str:
    """Read the bundled policy markdown, cached for the process lifetime."""
    global _policies_cache
    if _policies_cache is not None:
        return _policies_cache

    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "knowledge_base" / "policies.md",
        Path.cwd() / "knowledge_base" / "policies.md",
        here / "knowledge_base" / "policies.md",
    ]
    for path in candidates:
        try:
            if path.exists():
                _policies_cache = path.read_text(encoding="utf-8")
                return _policies_cache
        except OSError:
            continue
    _policies_cache = ""
    return _policies_cache


@app.route("/api/policy", methods=["POST"])
def policy():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return Response("Server is missing ANTHROPIC_API_KEY.", status=500)

    data = request.get_json(force=True, silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return Response("Missing question.", status=400)

    policies = load_policies()
    if not policies:
        return Response("Policy document is unavailable on the server.", status=500)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        f"POLICY DOCUMENT:\n\n{policies}\n\n---\n\n"
        f"Traveler's question: {question}"
    )

    def generate():
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=1500,
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
