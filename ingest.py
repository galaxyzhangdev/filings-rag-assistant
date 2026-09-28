"""Download, parse, and chunk a company's latest 10-K filings, cached by ticker."""
import json
from pathlib import Path

import requests
import tiktoken
from bs4 import BeautifulSoup

from filings import HEADERS, get_latest_10k_filings

DATA_DIR = Path("data")
ENCODING = tiktoken.get_encoding("cl100k_base")


def extract_text(html: str) -> str:
    """Strip scripts/styles from filing HTML and return the remaining visible text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into ~chunk_size-token windows with overlap, using tiktoken for token counts."""
    tokens = ENCODING.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        window = tokens[start : start + chunk_size]
        chunks.append(ENCODING.decode(window))
        start += chunk_size - overlap
    return chunks


def ingest_ticker(ticker: str) -> list[dict]:
    """Return a ticker's filing chunks, using the on-disk cache if present, else fetch+chunk+cache."""
    cache_path = DATA_DIR / f"{ticker.upper()}_chunks.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    chunks = []
    for filing in get_latest_10k_filings(ticker):
        resp = requests.get(filing["document_url"], headers=HEADERS)
        resp.raise_for_status()
        text = extract_text(resp.text)
        for piece in chunk_text(text):
            chunks.append({"ticker": ticker.upper(), "year": filing["year"], "text": piece})

    DATA_DIR.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps(chunks))
    return chunks


if __name__ == "__main__":
    for ticker in ("GOOGL", "MU"):
        chunks = ingest_ticker(ticker)
        print(f"{ticker}: {len(chunks)} chunks")
