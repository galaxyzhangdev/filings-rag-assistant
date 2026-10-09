"""Resolve a ticker to its latest 10-K filings via SEC EDGAR, and detect companies named in a question."""
import json
import re
from pathlib import Path

import requests

# SEC requires a descriptive User-Agent with contact info on every request.
HEADERS = {"User-Agent": "filings-rag-assistant galaxy.zcr@gmail.com"}

# Local copy of SEC's ticker index (not ingest.DATA_DIR: ingest imports this module, so that would be circular).
COMPANIES_PATH = Path("data/company_tickers.json")
# Real tickers that, written in uppercase in a question, almost always mean the acronym/word, not the company.
IGNORED_TICKERS = {"AI", "IT", "USA", "ON", "ALL", "NOW", "HBM", "TV", "PC", "AR", "EU", "UK"}
# Everyday names that don't match the SEC title (e.g. "MICRON TECHNOLOGY INC"). Kept deliberately small.
ALIASES = {"google": "GOOGL", "micron": "MU", "amazon": "AMZN", "meta": "META"}
# Legal-form words dropped from SEC titles before matching names.
SUFFIXES = {"inc", "corp", "corporation", "co", "ltd", "holdings"}


def resolve_cik(ticker: str) -> str:
    """Look up a ticker's zero-padded 10-digit CIK from SEC's ticker index."""
    resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=HEADERS, timeout=60)
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return f"{entry['cik_str']:010d}"
    raise ValueError(f"Ticker not found: {ticker}")


def get_latest_10k_filings(ticker: str, count: int = 2) -> list[dict]:
    """Return metadata (year, accession number, document URL) for a ticker's most recent 10-K filings."""
    cik = resolve_cik(ticker)
    resp = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=HEADERS, timeout=60)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]

    filings = []
    for form, accession, primary_doc, filing_date in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"], recent["filingDate"]
    ):
        if form == "10-K":
            accession_nodash = accession.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{primary_doc}"
            filings.append({"year": filing_date[:4], "accession_number": accession, "document_url": url})
            if len(filings) == count:
                break

    # Fail here, before ingest caches anything: an empty result (e.g. a 20-F filer) would otherwise be cached
    # as [] and break embedding on every later run until the cache file was deleted by hand.
    if not filings:
        raise ValueError(f"No 10-K filings found for ticker: {ticker}")
    return filings


def load_companies() -> list[dict]:
    """Return SEC's ticker index entries ({cik_str, ticker, title}), downloading it to data/ once if not cached."""
    if not COMPANIES_PATH.exists():
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=HEADERS, timeout=60)
        resp.raise_for_status()
        COMPANIES_PATH.parent.mkdir(exist_ok=True)
        COMPANIES_PATH.write_text(resp.text)
    return list(json.loads(COMPANIES_PATH.read_text()).values())


def normalize_title(title: str) -> str:
    """Lowercase a company title and drop /XX/ state tags, punctuation, and legal suffixes (Inc., Corp., ...)."""
    words = re.sub(r"[^a-z0-9]+", " ", re.sub(r"/\w+/", " ", title.lower())).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def find_tickers(question: str, companies: list[dict]) -> dict[str, list[str]]:
    """Detect companies in a question; returns {matched phrase: candidate tickers}, one candidate per company.

    A phrase with several candidates is ambiguous (the caller must ask, never guess). A company with several
    tickers (Alphabet: GOOGL, GOOG, ...) is reported once, under its first-listed ticker.
    Tickers match as uppercase words of 2+ letters; names match as whole words, only when the first word is
    capitalized in the question, so common-word names ("on target") don't match.
    """
    # Each company (CIK) is reported under its first-listed ticker; SEC lists the main share class first.
    primary, ticker_cik = {}, {}
    for c in companies:
        primary.setdefault(c["cik_str"], c["ticker"])
        ticker_cik[c["ticker"]] = c["cik_str"]

    # Normalized name -> companies (CIKs) sharing it; names under 4 chars are too likely to be ordinary words.
    names = {}
    for c in companies:
        name = normalize_title(c["title"])
        if len(name) < 4:
            continue
        ciks = names.setdefault(name, [])
        if c["cik_str"] not in ciks:
            ciks.append(c["cik_str"])
    for alias, ticker in ALIASES.items():
        if ticker in ticker_cik:
            names[alias] = [ticker_cik[ticker]]

    # Scan the question's words: each word as a ticker, and each capitalized word as the start of a name.
    words = re.findall(r"[A-Za-z0-9]+", question)
    max_words = max((name.count(" ") + 1 for name in names), default=0)
    found = {}
    for i, word in enumerate(words):
        if word.isalpha() and word.isupper() and len(word) >= 2 and word in ticker_cik and word not in IGNORED_TICKERS:
            found[word] = [primary[ticker_cik[word]]]
        if not word[0].isupper():
            continue
        for n in range(1, min(max_words, len(words) - i) + 1):
            phrase = " ".join(words[i : i + n]).lower()
            if phrase in names:
                found[phrase] = [primary[cik] for cik in names[phrase]]
    return found


if __name__ == "__main__":
    for ticker in ("GOOGL", "MU"):
        print(f"\n{ticker}:")
        for f in get_latest_10k_filings(ticker):
            print(f"  {f['year']}  {f['document_url']}")
