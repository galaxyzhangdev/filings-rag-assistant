"""Self-check: embedding batching and cache-skip logic, with mocked HTTP (no real API calls/cost)."""
import json
from unittest.mock import patch

from embed import DATA_DIR, embed_texts, embed_ticker


class FakeResponse:
    def __init__(self, n):
        self._n = n
        self.status_code = 200
        self.headers = {}

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": [{"embedding": [0.0, 0.0]} for _ in range(self._n)]}


def fake_post(url, headers, json):
    return FakeResponse(len(json["input"]))


with patch("embed.requests.post", side_effect=fake_post) as mock_post:
    embeddings = embed_texts([f"chunk {i}" for i in range(250)])
    assert len(embeddings) == 250
    assert mock_post.call_count == 3  # 250 texts / batch size 100 -> 3 calls

# A ticker whose cached chunks already have embeddings should skip re-embedding entirely.
DATA_DIR.mkdir(exist_ok=True)
test_cache = DATA_DIR / "TEST_chunks.json"
test_cache.write_text(json.dumps([{"ticker": "TEST", "year": "2024", "text": "x", "embedding": [1.0]}]))
with patch("embed.requests.post") as mock_post:
    chunks = embed_ticker("TEST")
    assert mock_post.call_count == 0
    assert chunks[0]["embedding"] == [1.0]
test_cache.unlink()

print("ok")
