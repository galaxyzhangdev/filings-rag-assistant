"""Retrieve the most relevant filing chunks for a question via cosine similarity search."""
import numpy as np

from embed import embed_texts, embed_ticker

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


def retrieve(question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5) -> list[dict]:
    """Embed the question and return the top_k most similar chunks (by cosine similarity) for each ticker.

    Retrieving per ticker (rather than one global top-k across all tickers combined) guarantees every
    ticker is represented in the context, which matters for cross-company questions: a single global
    top-k can otherwise end up dominated by whichever company's chunks happen to score higher.
    """
    question_vector = np.array(embed_texts([question])[0])

    results = []
    for ticker in tickers:
        chunks = embed_ticker(ticker)
        chunk_vectors = np.array([c["embedding"] for c in chunks])

        # Cosine similarity: dot product of each chunk vector with the question vector, divided by their norms.
        similarities = (chunk_vectors @ question_vector) / (
            np.linalg.norm(chunk_vectors, axis=1) * np.linalg.norm(question_vector)
        )

        top_indices = np.argsort(similarities)[::-1][:top_k]
        results.extend(
            {"ticker": chunks[i]["ticker"], "year": chunks[i]["year"], "text": chunks[i]["text"], "score": float(similarities[i])}
            for i in top_indices
        )

    return sorted(results, key=lambda r: r["score"], reverse=True)


if __name__ == "__main__":
    for result in retrieve("Which company had higher revenue, Alphabet or Micron?"):
        print(f"{result['score']:.3f}  {result['ticker']} {result['year']}  {result['text'][:80]!r}")
