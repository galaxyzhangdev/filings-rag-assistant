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

print("ok")
