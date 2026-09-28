"""Self-check: Chroma-based retrieval ranks the closest chunk first, with no real API calls."""
from unittest.mock import patch

from embed import collection
from retrieve import retrieve

DIM = 1536  # must match the collection's real embedding dimension (text-embedding-3-small)


def _pad(x, y):
    """Extend a 2D toy vector to the collection's real dimension, with zeros in the extra slots
    (zeros don't affect dot product or norm, so the intended cosine similarity is unchanged)."""
    return [x, y] + [0.0] * (DIM - 2)


def _add(ticker, chunks):
    collection.add(
        ids=[f"{ticker}_{i}" for i in range(len(chunks))],
        embeddings=[c["embedding"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{"ticker": ticker, "year": c["year"]} for c in chunks],
    )


fake_chunks = [
    {"year": "2024", "text": "far", "embedding": _pad(1.0, 0.0)},
    {"year": "2024", "text": "close", "embedding": _pad(0.9, 0.1)},
    {"year": "2024", "text": "exact", "embedding": _pad(0.0, 1.0)},
]
_add("AAA", fake_chunks)

with patch("retrieve.embed_texts", return_value=[_pad(0.0, 1.0)]):
    results = retrieve("question", tickers=("AAA",), top_k=2)

assert len(results) == 2
assert results[0]["text"] == "exact"
assert results[0]["score"] > results[1]["score"]
collection.delete(where={"ticker": "AAA"})

# Per-ticker retrieval must guarantee both tickers appear, even when one scores much lower overall
# (this is the cross-company bug: a single global top-k could otherwise drop the lower-scoring ticker).
_add("HIGH", [
    {"year": "2024", "text": "high1", "embedding": _pad(0.0, 1.0)},
    {"year": "2024", "text": "high2", "embedding": _pad(0.1, 0.9)},
])
_add("LOW", [
    {"year": "2024", "text": "low1", "embedding": _pad(0.9, 0.1)},
    {"year": "2024", "text": "low2", "embedding": _pad(1.0, 0.0)},
])

with patch("retrieve.embed_texts", return_value=[_pad(0.0, 1.0)]):
    results = retrieve("question", tickers=("HIGH", "LOW"), top_k=1)

assert {r["ticker"] for r in results} == {"HIGH", "LOW"}
assert len(results) == 2

collection.delete(where={"ticker": "HIGH"})
collection.delete(where={"ticker": "LOW"})

print("ok")
