"""Self-check: embedding batching, 429 retry, and Chroma cache-skip logic, with mocked HTTP (no real API calls/cost)."""
import os
import tempfile

# Run with no .env and no real data: a dummy key (embed.py reads it at import; all API calls are mocked) and a
# throwaway Chroma dir (removed at exit), so this test never reads or writes data/chroma. Must precede imports.
os.environ["OPENAI_API_KEY"] = "test-dummy"
_chroma_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["CHROMA_PATH"] = _chroma_dir.name

from unittest.mock import patch

from embed import collection, embed_texts, embed_ticker

DIM = 1536  # text-embedding-3-small's dimension; Chroma fixes a collection's dimension on first add


class FakeResponse:
    def __init__(self, n, status_code=200, headers=None):
        self._n = n
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": [{"embedding": [0.0, 0.0]} for _ in range(self._n)]}


def fake_post(url, headers, json, timeout):
    return FakeResponse(len(json["input"]))


with patch("embed.requests.post", side_effect=fake_post) as mock_post:
    embeddings = embed_texts([f"chunk {i}" for i in range(250)])
    assert len(embeddings) == 250
    assert mock_post.call_count == 3  # 250 texts / batch size 100 -> 3 calls

# A 429 is retried after the Retry-After wait (sleep mocked), and the next 200 response is used.
responses = [FakeResponse(1, status_code=429, headers={"Retry-After": "2"}), FakeResponse(1)]
with patch("embed.requests.post", side_effect=responses) as mock_post, patch("embed.time.sleep") as mock_sleep:
    assert len(embed_texts(["x"])) == 1
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(2.0)

# A ticker not yet in the Chroma collection should be embedded and stored there.
fake_chunks = [{"ticker": "TEST", "year": "2024", "text": "hello world"}]
with patch("embed.ingest_ticker", return_value=fake_chunks), \
     patch("embed.embed_texts", return_value=[[1.0] + [0.0] * (DIM - 1)]) as mock_embed:
    embed_ticker("TEST")
    assert mock_embed.call_count == 1
    stored = collection.get(where={"ticker": "TEST"})
    assert stored["documents"] == ["hello world"]

# A ticker whose chunks are already in Chroma should skip re-embedding entirely.
with patch("embed.embed_texts") as mock_embed:
    embed_ticker("TEST")
    assert mock_embed.call_count == 0

print("ok")
