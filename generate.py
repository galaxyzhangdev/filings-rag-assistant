"""Generate an answer to a question using retrieved filing chunks as context."""
import json
import time

import requests

from embed import OPENAI_HEADERS
from retrieve import DEFAULT_TICKERS, retrieve

SYSTEM_PROMPT = (
    "You are a financial analyst assistant. Answer the question using ONLY "
    "the excerpts below, taken from SEC 10-K filings. If the answer isn't "
    "contained in the excerpts, say you don't know instead of guessing."
)


def _build_prompt(
    question: str, top_k: int, method: str, tickers: tuple[str, ...]
) -> tuple[list[dict], str, list[dict]]:
    """Retrieve chunks for a question and build the chat messages; returns (chunks, context, messages).

    Shared by answer() and print_answer_streaming() so both send the model exactly the same prompt.
    """
    chunks = retrieve(question, tickers=tickers, top_k=top_k, method=method)
    context = "\n\n".join(f"[{c['ticker']} {c['year']}]\n{c['text']}" for c in chunks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {question}"},
    ]
    return chunks, context, messages


def answer(
    question: str, top_k: int = 5, method: str = "vector", tickers: tuple[str, ...] = DEFAULT_TICKERS
) -> dict:
    """Retrieve relevant filing chunks, stuff them into a prompt, and call gpt-4.1-mini for an answer.

    Returns the answer text along with the retrieved context (as one prompt string and as the raw chunk
    list), token usage, and latency (retrieval + generation), so callers (evaluation, the API) can score
    and log the full round trip.
    `method` picks the retrieval method ("vector" or "hybrid"); `tickers` picks which companies to search.
    """
    start = time.monotonic()
    chunks, context, messages = _build_prompt(question, top_k, method, tickers)
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=OPENAI_HEADERS,
        json={"model": "gpt-4.1-mini", "messages": messages},
        timeout=60,
    )
    latency = time.monotonic() - start
    resp.raise_for_status()
    data = resp.json()

    return {
        "answer": data["choices"][0]["message"]["content"],
        "context": context,
        "chunks": chunks,
        "usage": data["usage"],
        "latency": latency,
    }


def print_answer_streaming(
    question: str, top_k: int = 5, method: str = "vector", tickers: tuple[str, ...] = DEFAULT_TICKERS
) -> None:
    """Like answer(), but prints the response as it streams in from the API (CLI use only)."""
    _, _, messages = _build_prompt(question, top_k, method, tickers)
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=OPENAI_HEADERS,
        json={"model": "gpt-4.1-mini", "messages": messages, "stream": True},
        stream=True,
        timeout=60,
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
            print(delta, end="", flush=True)
    print()


if __name__ == "__main__":
    while True:
        question = input("\nQuestion: ")
        if question.strip().lower() in ("exit", "quit"):
            break
        print("\nAnswer: ", end="")
        print_answer_streaming(question)
        print()
