"""Embed chunked filing text using OpenAI's text-embedding-3-small, stored in a local Chroma collection."""
import os
import time
from pathlib import Path

import chromadb
import requests

from ingest import ingest_ticker

BATCH_SIZE = 100
MAX_RETRIES = 5

# Chroma: local embedded vector database, persisted to disk under data/chroma, no server to run.
# "hnsw:space": "cosine" makes query distances directly comparable to the old cosine-similarity scores.
_client = chromadb.PersistentClient(path="data/chroma")
collection = _client.get_or_create_collection("filing_chunks", metadata={"hnsw:space": "cosine"})


def _load_env():
    """Load OPENAI_API_KEY from .env into the environment, if it isn't set already."""
    if "OPENAI_API_KEY" in os.environ:
        return
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_env()
OPENAI_HEADERS = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts via OpenAI's API, batching requests and retrying on transient rate limits."""
    embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        for attempt in range(MAX_RETRIES):
            resp = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers=OPENAI_HEADERS,
                json={"model": "text-embedding-3-small", "input": batch},
            )
            if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(float(resp.headers.get("Retry-After", 5)))
                continue
            resp.raise_for_status()
            break
        embeddings.extend(item["embedding"] for item in resp.json()["data"])
    return embeddings


# Previous version: embeddings stored back into the ticker's chunk JSON file (a local .json cache),
# checked via an "embedding" field on the first chunk. Kept here, commented out, for comparison -- see
# NOTES.md / INTERVIEW_NOTES.md Step 3 for why this was upgraded to Chroma.
#
# def embed_ticker(ticker: str) -> list[dict]:
#     """Return a ticker's chunks with embeddings added, embedding and caching them only if not already done."""
#     chunks = ingest_ticker(ticker)
#     if chunks and "embedding" in chunks[0]:
#         return chunks
#
#     embeddings = embed_texts([c["text"] for c in chunks])
#     for chunk, embedding in zip(chunks, embeddings):
#         chunk["embedding"] = embedding
#
#     cache_path = DATA_DIR / f"{ticker.upper()}_chunks.json"
#     cache_path.write_text(json.dumps(chunks))
#     return chunks


def embed_ticker(ticker: str) -> None:
    """Embed a ticker's chunks and store them in the Chroma collection, skipping if already stored."""
    ticker = ticker.upper()
    if collection.get(where={"ticker": ticker}, limit=1)["ids"]:
        return

    chunks = ingest_ticker(ticker)
    embeddings = embed_texts([c["text"] for c in chunks])
    collection.add(
        ids=[f"{ticker}_{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[{"ticker": ticker, "year": c["year"]} for c in chunks],
    )


if __name__ == "__main__":
    for ticker in ("GOOGL", "MU"):
        embed_ticker(ticker)
        stored = collection.get(where={"ticker": ticker})
        print(f"{ticker}: {len(stored['ids'])} chunks embedded")
