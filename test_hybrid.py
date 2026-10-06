"""Self-check: tokenizer, RRF fusion, and hybrid per-ticker retrieval, with no real API calls."""
import os

os.environ["OPENAI_API_KEY"] = "test-dummy"  # embed.py reads the key at import time; all API calls are mocked

from unittest.mock import patch

from embed import collection
from retrieve import retrieve, rrf_fuse, tokenize

DIM = 1536  # must match the collection's real embedding dimension (text-embedding-3-small)

# Tokenizer keeps numbers and product terms as their own tokens.
tokens = tokenize("Revenue of $37.4 billion, HBM3E")
assert "37" in tokens and "4" in tokens and "hbm3e" in tokens, tokens

# A chunk present in both rank lists outranks chunks present in only one.
fused = rrf_fuse([["a", "b"], ["c", "a"]])
scores = dict(fused)
assert fused[0][0] == "a"
assert scores["a"] > scores["b"] and scores["a"] > scores["c"]

# Hybrid retrieval returns chunks for every requested ticker (the per-ticker guarantee still holds).
fake = {
    "HYA": ["hbm memory revenue grew", "unrelated text"],
    "HYB": ["search advertising revenue", "cloud revenue grew"],
}
try:
    for ticker, docs in fake.items():
        collection.add(
            ids=[f"{ticker}_{i}" for i in range(len(docs))],
            embeddings=[[1.0, float(i)] + [0.0] * (DIM - 2) for i in range(len(docs))],
            documents=docs,
            metadatas=[{"ticker": ticker, "year": "2024"} for _ in docs],
        )
    with patch("retrieve.embed_texts", return_value=[[1.0, 0.0] + [0.0] * (DIM - 2)]):
        results = retrieve("revenue grew", tickers=("HYA", "HYB"), top_k=1, method="hybrid")
    assert {r["ticker"] for r in results} == {"HYA", "HYB"}, results
    assert len(results) == 2
finally:
    for ticker in fake:
        collection.delete(where={"ticker": ticker})

print("ok")
