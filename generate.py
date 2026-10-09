"""Generate an answer to a question using retrieved filing chunks as context."""
import json
import time

import requests

from embed import OPENAI_HEADERS, embed_ticker, is_indexed
from filings import find_tickers, load_companies
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


def pick_tickers(question: str) -> tuple[str, ...]:
    """Pick the tickers a CLI question is about, offering to index any that aren't indexed yet (CLI use only).

    Falls back to DEFAULT_TICKERS when no company is detected; returns () when nothing is left to search.
    Never guesses: an ambiguous name asks the user to pick, and indexing (paid embeddings) needs an explicit "y".
    """
    companies = load_companies()
    matches = find_tickers(question, companies)
    if not matches:
        print(f"No company detected — searching {', '.join(DEFAULT_TICKERS)}")
        return DEFAULT_TICKERS

    titles = {c["ticker"]: c["title"] for c in companies}
    kept, skipped = [], []
    for phrase, candidates in matches.items():
        # Ambiguous name: list the candidates and let the user pick; blank or invalid input skips the phrase.
        ticker = candidates[0]
        if len(candidates) > 1:
            print(f'"{phrase}" matches several companies:')
            for n, t in enumerate(candidates, 1):
                print(f"  {n}) {t}  {titles[t]}")
            choice = input("Pick a number (blank to skip): ").strip()
            if not (choice.isdigit() and 1 <= int(choice) <= len(candidates)):
                continue
            ticker = candidates[int(choice) - 1]
        if ticker in kept or ticker in skipped:
            continue

        # Not indexed yet: only an explicit "y" triggers the (paid) ingest + embed run.
        if not is_indexed(ticker):
            if input(f"{ticker} is not indexed. Index now? (~30s, < $0.01) [y/N] ").strip().lower() != "y":
                skipped.append(ticker)
                continue
            try:
                embed_ticker(ticker)
            except ValueError as e:  # e.g. a foreign filer with no 10-K
                print(e)
                skipped.append(ticker)
                continue
        kept.append(ticker)

    if not kept:
        print("No indexed companies to search.")
        return ()
    if skipped:
        print(f"Skipping {', '.join(skipped)} (not indexed) — answering from {', '.join(kept)} only.")
    return tuple(kept)


if __name__ == "__main__":
    while True:
        question = input("\nQuestion: ")
        if question.strip().lower() in ("exit", "quit"):
            break
        tickers = pick_tickers(question)
        if not tickers:
            continue
        print("\nAnswer: ", end="")
        print_answer_streaming(question, tickers=tickers)
        print()
