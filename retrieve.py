"""Retrieve the most relevant filing chunks for a question via Chroma vector search, optionally fused with BM25."""
import re

from rank_bm25 import BM25Okapi

from embed import collection, embed_texts, embed_ticker

DEFAULT_TICKERS = ("GOOGL", "MU")
CANDIDATES = 20  # per-ticker candidates taken from each of vector search and BM25 before RRF fusion


# Previous version: one global top_k across all tickers' chunks combined. Kept here, commented out,
# for comparison -- see NOTES.md / INTERVIEW_NOTES.md Step 4 for what broke and why. In short: for
# cross-company questions, a single global ranking could be dominated by one ticker's chunks, so the
# other company's data sometimes never made the cut.
# Reference only, no longer runnable: embed_ticker() no longer returns chunks with embeddings, and numpy isn't imported.
#
# def retrieve(question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5) -> list[dict]:
#     """Embed the question and return the top_k most similar chunks (by cosine similarity) across the given tickers."""
#     chunks = [chunk for ticker in tickers for chunk in embed_ticker(ticker)]
#     chunk_vectors = np.array([c["embedding"] for c in chunks])
#     question_vector = np.array(embed_texts([question])[0])
#
#     # Cosine similarity: dot product of each chunk vector with the question vector, divided by their norms.
#     similarities = (chunk_vectors @ question_vector) / (
#         np.linalg.norm(chunk_vectors, axis=1) * np.linalg.norm(question_vector)
#     )
#
#     top_indices = np.argsort(similarities)[::-1][:top_k]
#     return [
#         {"ticker": chunks[i]["ticker"], "year": chunks[i]["year"], "text": chunks[i]["text"], "score": float(similarities[i])}
#         for i in top_indices
#     ]


# Previous version: per-ticker top_k, but computed by hand with numpy against every chunk's embedding
# loaded from the JSON cache. Kept here, commented out, for comparison -- see NOTES.md /
# INTERVIEW_NOTES.md Step 4 "Before vs. after" for why this was upgraded to Chroma.
# Reference only, no longer runnable: embed_ticker() no longer returns chunks with embeddings, and numpy isn't imported.
#
# def retrieve(question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5) -> list[dict]:
#     """Embed the question and return the top_k most similar chunks (by cosine similarity) for each ticker."""
#     question_vector = np.array(embed_texts([question])[0])
#
#     results = []
#     for ticker in tickers:
#         chunks = embed_ticker(ticker)
#         chunk_vectors = np.array([c["embedding"] for c in chunks])
#
#         # Cosine similarity: dot product of each chunk vector with the question vector, divided by their norms.
#         similarities = (chunk_vectors @ question_vector) / (
#             np.linalg.norm(chunk_vectors, axis=1) * np.linalg.norm(question_vector)
#         )
#
#         top_indices = np.argsort(similarities)[::-1][:top_k]
#         results.extend(
#             {"ticker": chunks[i]["ticker"], "year": chunks[i]["year"], "text": chunks[i]["text"], "score": float(similarities[i])}
#             for i in top_indices
#         )
#
#     return sorted(results, key=lambda r: r["score"], reverse=True)


# Previous version: vector-only Chroma retrieval (per-ticker top_k). Kept here, commented out, for
# comparison -- see NOTES.md / INTERVIEW_NOTES.md Step 7 for why a hybrid (BM25 + vector) option was added.
#
# def retrieve(question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5) -> list[dict]:
#     """Embed the question and return the top_k most similar chunks (via Chroma) for each ticker.
#
#     Retrieving per ticker (rather than one global top-k across all tickers combined) guarantees every
#     ticker is represented in the context, which matters for cross-company questions: a single global
#     top-k can otherwise end up dominated by whichever company's chunks happen to score higher.
#     """
#     for ticker in tickers:
#         embed_ticker(ticker)  # ensure this ticker's chunks are embedded and stored in Chroma
#
#     question_vector = embed_texts([question])[0]
#
#     results = []
#     for ticker in tickers:
#         hits = collection.query(
#             query_embeddings=[question_vector],
#             n_results=top_k,
#             where={"ticker": ticker.upper()},
#         )
#         # Chroma's collection space is cosine distance (1 - cosine similarity); flip it back to a score
#         # so a higher number still means "more similar", matching the old cosine-similarity convention.
#         results.extend(
#             {"ticker": meta["ticker"], "year": meta["year"], "text": doc, "score": 1 - distance}
#             for doc, meta, distance in zip(hits["documents"][0], hits["metadatas"][0], hits["distances"][0])
#         )
#
#     return sorted(results, key=lambda r: r["score"], reverse=True)


def tokenize(text: str) -> list[str]:
    """Lowercase and split into word tokens; keeps numbers and terms like "HBM" as their own tokens."""
    return re.findall(r"\w+", text.lower())


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score each id by the sum of 1/(k + rank) over every list it appears in (rank from 1)."""
    scores: dict[str, float] = {}
    for ranked_ids in rank_lists:
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


_bm25_cache: dict[str, tuple] = {}


def _bm25_index(ticker: str) -> tuple:
    """Build (once, in memory) a BM25 index over a ticker's chunks in Chroma; returns (bm25, ids, docs, metas)."""
    # ponytail: cache is never invalidated -- fine since a ticker's chunks are written once; rebuild if that changes.
    if ticker not in _bm25_cache:
        stored = collection.get(where={"ticker": ticker}, include=["documents", "metadatas"])
        bm25 = BM25Okapi([tokenize(doc) for doc in stored["documents"]])
        _bm25_cache[ticker] = (bm25, stored["ids"], stored["documents"], stored["metadatas"])
    return _bm25_cache[ticker]


def retrieve(
    question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5, method: str = "vector"
) -> list[dict]:
    """Return the top_k chunks per ticker for a question, via "vector" (Chroma) or "hybrid" (BM25 + vector, RRF).

    Retrieval stays per ticker (rather than one global top-k) so every ticker is represented in the context,
    which cross-company questions need. Hybrid scores are RRF scores, not cosine similarity.
    """
    if method not in ("vector", "hybrid"):
        raise ValueError(f"unknown retrieval method: {method!r}")

    for ticker in tickers:
        embed_ticker(ticker)  # ensure this ticker's chunks are embedded and stored in Chroma

    question_vector = embed_texts([question])[0]

    results = []
    for ticker in tickers:
        ticker = ticker.upper()
        if method == "vector":
            hits = collection.query(query_embeddings=[question_vector], n_results=top_k, where={"ticker": ticker})
            # Chroma's collection space is cosine distance (1 - cosine similarity); flip it back to a score.
            results.extend(
                {"ticker": meta["ticker"], "year": meta["year"], "text": doc, "score": 1 - distance}
                for doc, meta, distance in zip(hits["documents"][0], hits["metadatas"][0], hits["distances"][0])
            )
            continue

        # Hybrid: top CANDIDATES from vector search and from BM25, fused by rank with RRF.
        vector_ids = collection.query(
            query_embeddings=[question_vector], n_results=CANDIDATES, where={"ticker": ticker}, include=[]
        )["ids"][0]
        bm25, ids, docs, metas = _bm25_index(ticker)
        bm25_scores = bm25.get_scores(tokenize(question))
        ranked = sorted(range(len(ids)), key=lambda i: bm25_scores[i], reverse=True)[:CANDIDATES]
        bm25_ids = [ids[i] for i in ranked if bm25_scores[i] > 0]  # drop non-matches so they add no rank noise

        position = {chunk_id: i for i, chunk_id in enumerate(ids)}
        for chunk_id, score in rrf_fuse([vector_ids, bm25_ids])[:top_k]:
            i = position[chunk_id]
            results.append({"ticker": metas[i]["ticker"], "year": metas[i]["year"], "text": docs[i], "score": score})

    return sorted(results, key=lambda r: r["score"], reverse=True)

if __name__ == "__main__":
    for result in retrieve("Which company had higher revenue, Alphabet or Micron?", method="hybrid"):
        print(f"{result['score']:.3f}  {result['ticker']} {result['year']}  {result['text'][:80]!r}")
