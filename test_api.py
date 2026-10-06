"""Self-check: API status codes and response shape, with generate.answer and the index check mocked (no network)."""
import os

os.environ["OPENAI_API_KEY"] = "test-dummy"  # embed.py reads the key at import time; all API calls are mocked

from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

# Mocked chunks use the real stored metadata types (year is a string in Chroma), so a type mismatch fails here.
fake_result = {
    "answer": "Alphabet had higher revenue.",
    "context": "[GOOGL 2026]\nRevenues were $402.8 billion.",
    "chunks": [{"ticker": "GOOGL", "year": "2026", "text": "Revenues were $402.8 billion.", "score": 0.03}],
    "usage": {"prompt_tokens": 40, "completion_tokens": 6, "total_tokens": 46},
    "latency": 0.5,
}

# Health check.
resp = client.get("/health")
assert resp.status_code == 200 and resp.json() == {"status": "ok"}

# Happy path: tickers are normalized and passed through, response has the documented shape.
with patch("api.is_indexed", return_value=True), patch("api.answer", return_value=fake_result) as mock_answer:
    resp = client.post("/ask", json={"question": " Who earned more? ", "tickers": ["googl", "MU"], "method": "hybrid", "top_k": 3})
assert resp.status_code == 200, resp.text
body = resp.json()
assert body["answer"] == fake_result["answer"]
assert body["context"] == fake_result["chunks"]
assert body["usage"]["total_tokens"] == 46 and body["latency"] == 0.5
mock_answer.assert_called_once_with("Who earned more?", top_k=3, method="hybrid", tickers=("GOOGL", "MU"))

# Empty / whitespace-only question -> 422, pipeline never called.
with patch("api.answer") as mock_answer:
    for question in ("", "   "):
        assert client.post("/ask", json={"question": question}).status_code == 422
    assert mock_answer.call_count == 0

# Ticker not indexed -> 400 naming it, pipeline never called (no lazy ingest inside a request).
with patch("api.is_indexed", side_effect=lambda t: t != "ZZZZ"), patch("api.answer") as mock_answer:
    resp = client.post("/ask", json={"question": "Revenue?", "tickers": ["GOOGL", "zzzz"]})
assert resp.status_code == 400 and "ZZZZ" in resp.json()["detail"], resp.text
assert mock_answer.call_count == 0

# Upstream OpenAI failure -> 502 with a fixed message; nothing from the exception leaks out.
leaky = requests.HTTPError("401 Unauthorized, headers={'Authorization': 'Bearer sk-secret'}")
with patch("api.is_indexed", return_value=True), patch("api.answer", side_effect=leaky):
    resp = client.post("/ask", json={"question": "Revenue?"})
assert resp.status_code == 502
assert "sk-secret" not in resp.text and "Bearer" not in resp.text and "Authorization" not in resp.text
assert resp.json() == {"detail": "Upstream model service failed."}

print("ok")
