"""Self-check: cosine similarity ranking picks the closest chunk first, with no real API calls."""
from unittest.mock import patch

from retrieve import retrieve

fake_chunks = [
    {"ticker": "AAA", "year": "2024", "text": "far", "embedding": [1.0, 0.0]},
    {"ticker": "AAA", "year": "2024", "text": "close", "embedding": [0.9, 0.1]},
    {"ticker": "AAA", "year": "2024", "text": "exact", "embedding": [0.0, 1.0]},
]

with patch("retrieve.embed_ticker", return_value=fake_chunks), \
     patch("retrieve.embed_texts", return_value=[[0.0, 1.0]]):
    results = retrieve("question", tickers=("AAA",), top_k=2)

assert len(results) == 2
assert results[0]["text"] == "exact"
assert results[0]["score"] > results[1]["score"]

# Per-ticker retrieval must guarantee both tickers appear, even when one scores much lower overall
# (this is the cross-company bug: a single global top-k could otherwise drop the lower-scoring ticker).
fake_chunks_by_ticker = {
    "HIGH": [
        {"ticker": "HIGH", "year": "2024", "text": "high1", "embedding": [0.0, 1.0]},
        {"ticker": "HIGH", "year": "2024", "text": "high2", "embedding": [0.1, 0.9]},
    ],
    "LOW": [
        {"ticker": "LOW", "year": "2024", "text": "low1", "embedding": [0.9, 0.1]},
        {"ticker": "LOW", "year": "2024", "text": "low2", "embedding": [1.0, 0.0]},
    ],
}

with patch("retrieve.embed_ticker", side_effect=lambda ticker: fake_chunks_by_ticker[ticker]), \
     patch("retrieve.embed_texts", return_value=[[0.0, 1.0]]):
    results = retrieve("question", tickers=("HIGH", "LOW"), top_k=1)

assert {r["ticker"] for r in results} == {"HIGH", "LOW"}
assert len(results) == 2

print("ok")
