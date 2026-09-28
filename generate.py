"""Generate an answer to a question using retrieved filing chunks as context."""
import json
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


def print_answer_streaming(question: str, top_k: int = 5, delay: float = 0.02) -> None:
    """Like answer(), but prints the response token-by-token as it streams in (CLI use only)."""
    chunks = retrieve(question, top_k=top_k)
    context = "\n\n".join(f"[{c['ticker']} {c['year']}]\n{c['text']}" for c in chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {question}"},
    ]
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=OPENAI_HEADERS,
        json={"model": "gpt-4.1-mini", "messages": messages, "stream": True},
        stream=True,
    )
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            break
        delta = json.loads(payload)["choices"][0]["delta"].get("content")
        if delta:
            for ch in delta:
                print(ch, end="", flush=True)
                time.sleep(delay)
    print()


if __name__ == "__main__":
    while True:
        question = input("\nQuestion: ")
        if question.strip().lower() in ("exit", "quit"):
            break
        print("\nAnswer: ", end="")
        print_answer_streaming(question)
        print()
