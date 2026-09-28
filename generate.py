"""Generate an answer to a question using retrieved filing chunks as context."""
import time

import requests

from embed import OPENAI_HEADERS
from retrieve import retrieve

SYSTEM_PROMPT = (
    "You are a financial analyst assistant. Answer the question using ONLY "
    "the excerpts below, taken from SEC 10-K filings. If the answer isn't "
    "contained in the excerpts, say you don't know instead of guessing."
)


def answer(question: str, top_k: int = 5) -> dict:
    """Retrieve relevant filing chunks, stuff them into a prompt, and call gpt-4.1-mini for an answer.

    Returns the answer text along with the retrieved context, token usage, and latency,
    so callers (e.g. evaluation) can score and log the full round trip.
    """
    chunks = retrieve(question, top_k=top_k)
    context = "\n\n".join(f"[{c['ticker']} {c['year']}]\n{c['text']}" for c in chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {question}"},
    ]
    start = time.monotonic()
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=OPENAI_HEADERS,
        json={"model": "gpt-4.1-mini", "messages": messages},
    )
    latency = time.monotonic() - start
    resp.raise_for_status()
    data = resp.json()

    return {
        "answer": data["choices"][0]["message"]["content"],
        "context": context,
        "usage": data["usage"],
        "latency": latency,
    }


if __name__ == "__main__":
    while True:
        question = input("Question: ")
        if question.strip().lower() in ("exit", "quit"):
            break
        print(f"\nAnswer: {answer(question)['answer']}\n")
