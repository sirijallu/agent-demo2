"""Retrieval over the Wanderly policy knowledge base (Agentic RAG).

The index (chunks + Voyage embeddings) is built by scripts/ingest_kb.py and
stored as kb_index.json in Vercel Blob. At query time we embed the query with
Voyage and rank chunks by cosine similarity.

Underscore prefix keeps Vercel from exposing this file as an API route.
"""

import math
import os
import time

import requests

BLOB_API_URL = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "12"
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3.5"
KB_INDEX_PATHNAME = "kb_index.json"
TOP_K = 4

_index_cache = None


class RagError(Exception):
    pass


def _blob_token() -> str:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()
    if not token or token.startswith("your-"):
        raise RagError("BLOB_READ_WRITE_TOKEN is not configured.")
    return token


def _voyage_key() -> str:
    key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if not key or key.startswith("your-"):
        raise RagError("VOYAGE_API_KEY is not configured.")
    return key


def load_index() -> dict:
    """Fetch kb_index.json from Vercel Blob, cached for the process lifetime."""
    global _index_cache
    if _index_cache is not None:
        return _index_cache

    token = _blob_token()
    res = requests.get(
        BLOB_API_URL,
        params={"prefix": KB_INDEX_PATHNAME, "limit": "10"},
        headers={"Authorization": f"Bearer {token}", "x-api-version": BLOB_API_VERSION},
        timeout=15,
    )
    res.raise_for_status()
    blobs = res.json().get("blobs", [])
    match = next((b for b in blobs if b.get("pathname") == KB_INDEX_PATHNAME), None)
    if match is None:
        raise RagError(
            f"{KB_INDEX_PATHNAME} not found in Blob storage — run scripts/ingest_kb.py first."
        )

    # The store is private, so downloading the blob also needs the token.
    res = requests.get(match["url"], headers={"Authorization": f"Bearer {token}"}, timeout=15)
    res.raise_for_status()
    _index_cache = res.json()
    return _index_cache


def embed(texts: list[str], input_type: str) -> list[list[float]]:
    # Voyage free-tier keys have tight per-minute rate limits; retry 429s.
    for attempt in range(4):
        res = requests.post(
            VOYAGE_API_URL,
            json={"input": texts, "model": VOYAGE_MODEL, "input_type": input_type},
            headers={"Authorization": f"Bearer {_voyage_key()}"},
            timeout=30,
        )
        if res.status_code == 429 and attempt < 3:
            time.sleep(2 ** (attempt + 1))
            continue
        res.raise_for_status()
        data = sorted(res.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def retrieve(query: str, top_k: int = TOP_K) -> str:
    """Return the top matching policy chunks formatted for a tool result."""
    query = (query or "").strip()
    if not query:
        return "Empty query — nothing retrieved."

    try:
        index = load_index()
        query_emb = embed([query], input_type="query")[0]
    except RagError as e:
        return f"Policy knowledge base unavailable: {e}"
    except requests.RequestException as e:
        return f"Policy knowledge base unavailable: {e.__class__.__name__}"

    scored = sorted(
        index["chunks"],
        key=lambda c: _cosine(query_emb, c["embedding"]),
        reverse=True,
    )[:top_k]

    parts = []
    for chunk in scored:
        parts.append(f"[{chunk['heading']}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts) if parts else "No matching policy sections found."


# Tool definition shared by the CLI and the web API.
POLICY_TOOL = {
    "name": "search_policies",
    "description": (
        "Search Wanderly's travel policy knowledge base. It covers: cancellation "
        "and refund rules (free-cancellation window, fee tiers by days before "
        "departure, refund timelines, change fees), baggage policies (carry-on and "
        "checked allowances, overweight/oversize fees, special items, lost baggage), "
        "and travel insurance (included protection, the TravelSafe plan, CFAR "
        "upgrade, exclusions, claims). Use this whenever the traveler asks about — "
        "or their trip would clearly benefit from — policy details. Results are "
        "excerpts from the official policy document."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language question about cancellation, baggage, or insurance policy",
            }
        },
        "required": ["query"],
    },
}
