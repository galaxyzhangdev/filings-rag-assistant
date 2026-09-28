"""Generate an answer to a question using retrieved filing chunks as context."""
import requests

from embed import OPENAI_HEADERS
from retrieve import retrieve

SYSTEM_PROMPT = (
    "You are a financial analyst assistant. Answer the question using ONLY "
    "the excerpts below, taken from SEC 10-K filings. If the answer isn't "
    "contained in the excerpts, say you don't know instead of guessing."
)


def answer(question: str, top_k: int = 5) -> str:
    """Retrieve relevant filing chunks, stuff them into a prompt, and call gpt-4.1-mini for an answer."""
    chunks = retrieve(question, top_k=top_k)
    context = "\n\n".join(f"[{c['ticker']} {c['year']}]\n{c['text']}" for c in chunks)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {question}"},
    ]
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=OPENAI_HEADERS,
        json={"model": "gpt-4.1-mini", "messages": messages},
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


if __name__ == "__main__":
    print(answer("What was Micron's revenue in fiscal 2025?"))
