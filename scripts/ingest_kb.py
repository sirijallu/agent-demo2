#!/usr/bin/env python3
"""Ingest the knowledge base into Vercel Blob for Agentic RAG.

Reads knowledge_base/*.md, chunks by markdown headings, embeds each chunk with
Voyage AI, and uploads the resulting index as kb_index.json to Vercel Blob.

Requires VOYAGE_API_KEY and BLOB_READ_WRITE_TOKEN in config.env (or the
environment). Re-run after editing any knowledge_base markdown file.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from _rag import (  # noqa: E402
    BLOB_API_URL,
    BLOB_API_VERSION,
    KB_INDEX_PATHNAME,
    VOYAGE_MODEL,
    _blob_token,
    embed,
)

MAX_CHUNK_CHARS = 1200


def chunk_markdown(text: str, source: str) -> list[dict]:
    """Split a markdown document into heading-scoped chunks.

    Each ###-or-higher heading starts a new chunk; oversized sections are split
    on paragraph boundaries. The heading trail (H1 > H2 > H3) is kept as
    context and prepended for embedding.
    """
    h1 = h2 = h3 = ""
    chunks: list[dict] = []
    buffer: list[str] = []

    def heading_trail() -> str:
        return " > ".join(part for part in (h1, h2, h3) if part)

    def flush():
        body = "\n".join(buffer).strip()
        buffer.clear()
        if not body:
            return
        paragraphs = re.split(r"\n\s*\n", body)
        piece = ""
        pieces = []
        for para in paragraphs:
            candidate = f"{piece}\n\n{para}".strip() if piece else para
            if len(candidate) > MAX_CHUNK_CHARS and piece:
                pieces.append(piece)
                piece = para
            else:
                piece = candidate
        if piece:
            pieces.append(piece)
        for p in pieces:
            chunks.append({"source": source, "heading": heading_trail(), "text": p})

    for line in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            if level == 1:
                h1, h2, h3 = title, "", ""
            elif level == 2:
                h2, h3 = title, ""
            else:
                h3 = title
        else:
            buffer.append(line)
    flush()
    return chunks


def upload_to_blob(pathname: str, payload: bytes) -> str:
    res = requests.put(
        f"{BLOB_API_URL}/?pathname={pathname}",
        data=payload,
        headers={
            "Authorization": f"Bearer {_blob_token()}",
            "x-api-version": BLOB_API_VERSION,
            "x-vercel-blob-access": "private",
            "x-allow-overwrite": "1",
            "x-content-type": "application/json",
            "x-add-random-suffix": "0",
        },
        timeout=30,
    )
    res.raise_for_status()
    return res.json()["url"]


def main() -> None:
    load_dotenv(dotenv_path=ROOT / "config.env")

    kb_files = sorted((ROOT / "knowledge_base").glob("*.md"))
    if not kb_files:
        sys.exit("No markdown files found in knowledge_base/")

    all_chunks: list[dict] = []
    for path in kb_files:
        chunks = chunk_markdown(path.read_text(encoding="utf-8"), source=path.name)
        print(f"{path.name}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"Embedding {len(all_chunks)} chunks with {VOYAGE_MODEL}...")
    embed_input = [f"{c['heading']}\n\n{c['text']}" for c in all_chunks]
    embeddings: list[list[float]] = []
    for start in range(0, len(embed_input), 64):
        embeddings.extend(embed(embed_input[start : start + 64], input_type="document"))

    for i, (chunk, emb) in enumerate(zip(all_chunks, embeddings)):
        chunk["id"] = i
        chunk["embedding"] = emb

    index = {
        "model": VOYAGE_MODEL,
        "created": int(time.time()),
        "chunks": all_chunks,
    }
    payload = json.dumps(index).encode("utf-8")
    print(f"Uploading {KB_INDEX_PATHNAME} ({len(payload) / 1024:.0f} KB) to Vercel Blob...")
    url = upload_to_blob(KB_INDEX_PATHNAME, payload)
    print(f"Done: {url}")


if __name__ == "__main__":
    main()
