"""Embed chunked filing text using OpenAI's text-embedding-3-small, cached alongside the chunks."""
import json
import os
import time
from pathlib import Path

import requests

from ingest import DATA_DIR, ingest_ticker

BATCH_SIZE = 100
MAX_RETRIES = 5


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


def embed_ticker(ticker: str) -> list[dict]:
    """Return a ticker's chunks with embeddings added, embedding and caching them only if not already done."""
    chunks = ingest_ticker(ticker)
    if chunks and "embedding" in chunks[0]:
        return chunks

    embeddings = embed_texts([c["text"] for c in chunks])
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    cache_path = DATA_DIR / f"{ticker.upper()}_chunks.json"
    cache_path.write_text(json.dumps(chunks))
    return chunks


if __name__ == "__main__":
    for ticker in ("GOOGL", "MU"):
        chunks = embed_ticker(ticker)
        print(f"{ticker}: {len(chunks)} chunks embedded, dim={len(chunks[0]['embedding'])}")
