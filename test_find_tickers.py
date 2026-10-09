"""Self-check: company detection in questions, and the CLI's index-on-demand prompt (no network, no OpenAI)."""
import io
import os
import tempfile
from contextlib import redirect_stdout

# Run with no .env and no real data: a dummy key (embed.py reads it at import; nothing here calls the API) and a
# throwaway Chroma dir (removed at exit), so this test never reads or writes data/chroma. Must precede imports.
os.environ["OPENAI_API_KEY"] = "test-dummy"
_chroma_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["CHROMA_PATH"] = _chroma_dir.name

from unittest.mock import patch

from filings import find_tickers
from generate import pick_tickers
from retrieve import DEFAULT_TICKERS

# Fake slice of SEC's company_tickers.json: Alphabet has two tickers on one CIK, "Toro" is two companies,
# and Target / Gartner (IT) / C3.ai (AI) / Hudbay (HBM) are common words that must not match casual text.
COMPANIES = [
    {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
    {"cik_str": 723125, "ticker": "MU", "title": "MICRON TECHNOLOGY INC"},
    {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    {"cik_str": 27419, "ticker": "TGT", "title": "TARGET CORP"},
    {"cik_str": 749251, "ticker": "IT", "title": "GARTNER INC"},
    {"cik_str": 1577526, "ticker": "AI", "title": "C3.ai, Inc."},
    {"cik_str": 1322422, "ticker": "HBM", "title": "Hudbay Minerals Inc."},
    {"cik_str": 737758, "ticker": "TTC", "title": "TORO CO"},
    {"cik_str": 1941131, "ticker": "TORO", "title": "TORO CORP."},
]


def tickers(question):
    """Flatten find_tickers' result to the list of candidate tickers, in question order."""
    return [t for candidates in find_tickers(question, COMPANIES).values() for t in candidates]


assert tickers("How did Tesla's revenue change?") == ["TSLA"]
assert tickers("Compare TSLA and MU") == ["TSLA", "MU"]
assert tickers("What is Google's revenue?") == ["GOOGL"]  # alias
assert tickers("on target for it all") == []
assert tickers("What did Nvidia say about AI demand?") == ["NVDA"]  # AI is an ignored ticker
assert tickers("What did Micron say about HBM demand?") == ["MU"]  # HBM = high-bandwidth memory, not Hudbay
assert find_tickers("How did Toro do?", COMPANIES) == {"toro": ["TTC", "TORO"]}  # ambiguous: two candidates
assert tickers("How did GOOG do?") == ["GOOGL"]  # secondary ticker -> the company's first-listed one


def run_pick(question, answers, indexed):
    """Run pick_tickers with mocked SEC data, Chroma state, user input, and embedding; return (result, embed mock, output)."""
    out = io.StringIO()
    with patch("generate.load_companies", return_value=COMPANIES), \
         patch("generate.is_indexed", side_effect=lambda t: t in indexed), \
         patch("generate.embed_ticker") as embed, \
         patch("builtins.input", side_effect=answers), \
         redirect_stdout(out):
        result = pick_tickers(question)
    return result, embed, out.getvalue()


result, embed, _ = run_pick("How did Tesla's revenue change?", ["y"], indexed=set())
assert result == ("TSLA",)
embed.assert_called_once_with("TSLA")

result, embed, out = run_pick("How did Tesla's revenue change?", ["N"], indexed=set())
assert result == ()
embed.assert_not_called()
assert "No indexed companies to search." in out

result, embed, out = run_pick("Compare Tesla and Micron", ["N"], indexed={"MU"})
assert result == ("MU",)
embed.assert_not_called()
assert "Skipping TSLA (not indexed) — answering from MU only." in out

result, _, out = run_pick("What were the main risk factors?", [], indexed=set())
assert result == DEFAULT_TICKERS
assert "No company detected — searching GOOGL, MU" in out

print("ok")
