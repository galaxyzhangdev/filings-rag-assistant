"""Resolve a ticker to its latest 10-K filings via SEC EDGAR."""
import requests

# SEC requires a descriptive User-Agent with contact info on every request.
HEADERS = {"User-Agent": "filings-rag-assistant galaxy.zcr@gmail.com"}


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


if __name__ == "__main__":
    for ticker in ("GOOGL", "MU"):
        print(f"\n{ticker}:")
        for f in get_latest_10k_filings(ticker):
            print(f"  {f['year']}  {f['document_url']}")
