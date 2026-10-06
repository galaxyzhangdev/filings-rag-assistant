"""Self-check: text extraction, chunking, and 10-K lookup (SEC mocked) work correctly, with no network calls."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from filings import get_latest_10k_filings
from ingest import chunk_text, extract_text, ingest_ticker, ENCODING

html = "<html><head><style>body{color:red}</style></head><body><script>alert(1)</script><p>Hello world.</p></body></html>"
text = extract_text(html)
assert "Hello world." in text
assert "alert" not in text
assert "color:red" not in text

long_text = "word " * 2000
chunks = chunk_text(long_text, chunk_size=500, overlap=50)
assert len(chunks) > 1
assert len(ENCODING.encode(chunks[0])) == 500
# Consecutive chunks should share the overlapping tail/head tokens.
assert ENCODING.encode(chunks[0])[-50:] == ENCODING.encode(chunks[1])[:50]

# Mocked SEC responses: the ticker index, one 10-K filer, and one 20-F filer (no 10-K at all).
SEC_JSON = {
    "company_tickers.json": {"0": {"cik_str": 1652044, "ticker": "GOOGL"}, "1": {"cik_str": 1046179, "ticker": "TSM"}},
    "CIK0001652044.json": {"filings": {"recent": {
        "form": ["4", "10-K", "10-K/A", "10-Q", "10-K", "10-K"],
        "accessionNumber": ["a-1", "0001652044-26-000018", "a-3", "a-4", "0001652044-25-000014", "a-6"],
        "primaryDocument": ["f4.xml", "goog-20251231.htm", "amend.htm", "q.htm", "goog-20241231.htm", "old.htm"],
        "filingDate": ["2026-03-01", "2026-02-05", "2025-06-01", "2025-04-25", "2025-02-05", "2024-01-31"],
    }}},
    "CIK0001046179.json": {"filings": {"recent": {
        "form": ["20-F", "6-K"], "accessionNumber": ["b-1", "b-2"],
        "primaryDocument": ["x.htm", "y.htm"], "filingDate": ["2026-04-01", "2026-03-01"],
    }}},
}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def fake_get(url, headers, timeout):
    return FakeResponse(SEC_JSON[url.rsplit("/", 1)[1]])


with patch("filings.requests.get", side_effect=fake_get):
    # Only exact "10-K" forms (not 10-K/A), newest first, stopping at count=2; URL uses the unpadded CIK
    # and the accession number without dashes.
    filings = get_latest_10k_filings("googl")
    assert [f["year"] for f in filings] == ["2026", "2025"], filings
    assert filings[0]["document_url"] == (
        "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm"
    ), filings

    # No 10-K: ingest must raise before writing its cache, so no empty [] cache file is left behind.
    with tempfile.TemporaryDirectory() as tmp, patch("ingest.DATA_DIR", Path(tmp)):
        try:
            ingest_ticker("TSM")
            raise AssertionError("expected ValueError for a ticker with no 10-K")
        except ValueError as e:
            assert "TSM" in str(e)
        assert not (Path(tmp) / "TSM_chunks.json").exists()

print("ok")
