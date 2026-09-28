"""Retrieve the most relevant filing chunks for a question via Chroma vector search."""
from embed import collection, embed_texts, embed_ticker

DEFAULT_TICKERS = ("GOOGL", "MU")


# Previous version: one global top_k across all tickers' chunks combined. Kept here, commented out,
# for comparison -- see NOTES.md / INTERVIEW_NOTES.md Step 4 for what broke and why. In short: for
# cross-company questions, a single global ranking could be dominated by one ticker's chunks, so the
# other company's data sometimes never made the cut.
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


def retrieve(question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5) -> list[dict]:
    """Embed the question and return the top_k most similar chunks (via Chroma) for each ticker.

    Retrieving per ticker (rather than one global top-k across all tickers combined) guarantees every
    ticker is represented in the context, which matters for cross-company questions: a single global
    top-k can otherwise end up dominated by whichever company's chunks happen to score higher.
    """
    for ticker in tickers:
        embed_ticker(ticker)  # ensure this ticker's chunks are embedded and stored in Chroma

    question_vector = embed_texts([question])[0]

    results = []
    for ticker in tickers:
        hits = collection.query(
            query_embeddings=[question_vector],
            n_results=top_k,
            where={"ticker": ticker.upper()},
        )
        # Chroma's collection space is cosine distance (1 - cosine similarity); flip it back to a score
        # so a higher number still means "more similar", matching the old cosine-similarity convention.
        results.extend(
            {"ticker": meta["ticker"], "year": meta["year"], "text": doc, "score": 1 - distance}
            for doc, meta, distance in zip(hits["documents"][0], hits["metadatas"][0], hits["distances"][0])
        )

    return sorted(results, key=lambda r: r["score"], reverse=True)


if __name__ == "__main__":
    for result in retrieve("Which company had higher revenue, Alphabet or Micron?"):
        print(f"{result['score']:.3f}  {result['ticker']} {result['year']}  {result['text'][:80]!r}")
