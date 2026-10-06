"""Self-check: eval answer caching, --no-cache regeneration, and the regression gate, with no real API calls."""
import os
import tempfile

# Run with no .env and no real data: a dummy key (embed.py reads it at import; all API calls are mocked) and a
# throwaway Chroma dir (removed at exit), so this test never reads or writes data/chroma. Must precede imports.
os.environ["OPENAI_API_KEY"] = "test-dummy"
_chroma_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["CHROMA_PATH"] = _chroma_dir.name

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

# --no-cache (use_cache=False) regenerates even when the question is already cached, and never touches the file.
no_cache_path = Path(_chroma_dir.name) / "eval_cache.json"
no_cache_path.write_text('{"vector::some question": {"answer": "stale"}}')
before = no_cache_path.read_bytes()
fake_judge = MagicMock()
fake_judge.evaluate.return_value = [SimpleNamespace(label="ok", score=1.0)]
with patch.object(eval_module, "CACHE_PATH", no_cache_path), \
     patch("eval.LLM"), \
     patch("eval.RetrievalRelevanceEvaluator", return_value=fake_judge), \
     patch("eval.FaithfulnessEvaluator", return_value=fake_judge), \
     patch("eval.create_classifier", return_value=fake_judge), \
     patch("eval.answer", return_value=fake_result) as mock_answer:
    results = eval_module.run_eval(eval_set=[{"question": "some question", "category": "factual"}], use_cache=False)
assert mock_answer.call_count == 1  # regenerated despite the cached entry
assert results[0]["answer"] == "42"
assert no_cache_path.read_bytes() == before  # cache file neither rewritten nor extended

# Gate: averages at or above every floor pass; one below fails and names the metric.
def _results(context_relevance):
    return [{"context_relevance": context_relevance, "groundedness": 1.0, "answer_relevance": 1.0}]

assert eval_module.gate_failures(_results(1.0)) == []
assert eval_module.gate_failures(_results(0.75)) == []  # exactly at the floor passes
failures = eval_module.gate_failures(_results(0.70))
assert len(failures) == 1 and failures[0].startswith("context_relevance"), failures

print("ok")
