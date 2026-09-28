"""Retrieve the most relevant filing chunks for a question via cosine similarity search."""
import numpy as np

from embed import embed_texts, embed_ticker

DEFAULT_TICKERS = ("GOOGL", "MU")


def retrieve(question: str, tickers: tuple[str, ...] = DEFAULT_TICKERS, top_k: int = 5) -> list[dict]:
    """Embed the question and return the top_k most similar chunks (by cosine similarity) across the given tickers."""
    chunks = [chunk for ticker in tickers for chunk in embed_ticker(ticker)]
    chunk_vectors = np.array([c["embedding"] for c in chunks])
    question_vector = np.array(embed_texts([question])[0])

    # Cosine similarity: dot product of each chunk vector with the question vector, divided by their norms.
    similarities = (chunk_vectors @ question_vector) / (
        np.linalg.norm(chunk_vectors, axis=1) * np.linalg.norm(question_vector)
    )

    top_indices = np.argsort(similarities)[::-1][:top_k]
    return [
        {"ticker": chunks[i]["ticker"], "year": chunks[i]["year"], "text": chunks[i]["text"], "score": float(similarities[i])}
        for i in top_indices
    ]


if __name__ == "__main__":
    for result in retrieve("What was Micron's revenue?"):
        print(f"{result['score']:.3f}  {result['ticker']} {result['year']}  {result['text'][:80]!r}")
