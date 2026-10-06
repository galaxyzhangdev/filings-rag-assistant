"""Self-check: eval answer caching skips re-generation on a repeat question, with no real API calls."""
import os
import tempfile

# Run with no .env and no real data: a dummy key (embed.py reads it at import; all API calls are mocked) and a
# throwaway Chroma dir (removed at exit), so this test never reads or writes data/chroma. Must precede imports.
os.environ["OPENAI_API_KEY"] = "test-dummy"
_chroma_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["CHROMA_PATH"] = _chroma_dir.name

from pathlib import Path
from unittest.mock import patch

import eval as eval_module

test_cache_path = Path("data/test_eval_cache.json")
fake_result = {"answer": "42", "context": "ctx", "usage": {"total_tokens": 10}, "latency": 0.1}

with patch.object(eval_module, "CACHE_PATH", test_cache_path), \
     patch("eval.answer", return_value=fake_result) as mock_answer:
    cache = {}
    first = eval_module.get_cached_answer("some question", cache)
    second = eval_module.get_cached_answer("some question", cache)
    assert mock_answer.call_count == 1  # second call should hit the cache, not regenerate

    # A different retrieval method must not reuse the vector entry.
    eval_module.get_cached_answer("some question", cache, method="hybrid")
    assert mock_answer.call_count == 2
    assert set(cache) == {"vector::some question", "hybrid::some question"}

assert first == second == fake_result
assert test_cache_path.exists()

test_cache_path.unlink()
print("ok")
