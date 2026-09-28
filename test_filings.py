"""Self-check: ticker lookup resolves a known CIK and returns 2 valid 10-K URLs."""
from filings import resolve_cik, get_latest_10k_filings

assert resolve_cik("AAPL") == "0000320193"

filings = get_latest_10k_filings("MU", count=2)
assert len(filings) == 2
assert all(f["document_url"].startswith("https://www.sec.gov/Archives/") for f in filings)
assert filings[0]["year"] > filings[1]["year"]  # most recent filing first

print("ok")
