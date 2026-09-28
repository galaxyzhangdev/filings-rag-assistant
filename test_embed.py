"""Self-check: embedding batching and Chroma cache-skip logic, with mocked HTTP (no real API calls/cost)."""
from unittest.mock import patch

from embed import collection, embed_texts, embed_ticker

DIM = 1536  # must match the collection's real embedding dimension (text-embedding-3-small)


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

collection.delete(where={"ticker": "TEST"})

print("ok")
