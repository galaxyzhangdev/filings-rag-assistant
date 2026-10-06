"""Self-check: tokenizer, RRF fusion, and hybrid per-ticker retrieval, with no real API calls."""
import os
import tempfile

# Run with no .env and no real data: a dummy key (embed.py reads it at import; all API calls are mocked) and a
# throwaway Chroma dir (removed at exit), so this test never reads or writes data/chroma. Must precede imports.
os.environ["OPENAI_API_KEY"] = "test-dummy"
_chroma_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["CHROMA_PATH"] = _chroma_dir.name

from unittest.mock import patch

from embed import collection
from retrieve import retrieve, rrf_fuse, tokenize

DIM = 1536  # text-embedding-3-small's dimension; Chroma fixes a collection's dimension on first add

# Tokenizer keeps numbers and product terms as their own tokens.
tokens = tokenize("Revenue of $37.4 billion, HBM3E")
assert "37" in tokens and "4" in tokens and "hbm3e" in tokens, tokens

# A chunk present in both rank lists outranks chunks present in only one.
fused = rrf_fuse([["a", "b"], ["c", "a"]])
scores = dict(fused)
assert fused[0][0] == "a"
assert scores["a"] > scores["b"] and scores["a"] > scores["c"]

# Hybrid retrieval keeps the per-ticker guarantee, and BM25 actually changes the result. Doc i's vector is
# [1, i], so vector search ranks doc 0 first. Only HYA's last (vector-farthest) doc contains the question's
# terms, so its positive BM25 score must lift it to the top. 3 docs per ticker: with 2, every BM25 IDF is <= 0.
fake = {
    "HYA": ["dram pricing improved", "nand inventory fell", "hbm3e shipments ramped"],
    "HYB": ["search advertising grew", "cloud backlog rose", "youtube subscriptions"],
}
for ticker, docs in fake.items():
    collection.add(
        ids=[f"{ticker}_{i}" for i in range(len(docs))],
        embeddings=[[1.0, float(i)] + [0.0] * (DIM - 2) for i in range(len(docs))],
        documents=docs,
        metadatas=[{"ticker": ticker, "year": "2024"} for _ in docs],
    )
with patch("retrieve.embed_texts", return_value=[[1.0, 0.0] + [0.0] * (DIM - 2)]):
    hybrid = retrieve("hbm3e shipments", tickers=("HYA", "HYB"), top_k=1, method="hybrid")
    vector = retrieve("hbm3e shipments", tickers=("HYA", "HYB"), top_k=1, method="vector")
assert {r["ticker"] for r in hybrid} == {"HYA", "HYB"} and len(hybrid) == 2, hybrid
hybrid_text = {r["ticker"]: r["text"] for r in hybrid}
assert hybrid_text["HYA"] == "hbm3e shipments ramped", hybrid  # BM25 match outranks the vector-closest doc
assert hybrid_text["HYB"] == "search advertising grew", hybrid  # no BM25 match: falls back to vector order
assert {r["ticker"]: r["text"] for r in vector}["HYA"] == "dram pricing improved", vector  # vector alone differs

print("ok")
