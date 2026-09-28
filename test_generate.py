"""Self-check: prompt construction and response parsing, with mocked HTTP (no real API calls/cost)."""
from unittest.mock import patch

from generate import answer

fake_chunks = [{"ticker": "MU", "year": "2025", "text": "Revenue was $37.4 billion.", "score": 0.9}]


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "Micron's revenue was $37.4 billion."}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 8, "total_tokens": 50},
        }


def fake_post(url, headers, json):
    # Confirm the retrieved chunk's text and the question both made it into the prompt sent to the API.
    sent_text = json["messages"][1]["content"]
    assert "Revenue was $37.4 billion." in sent_text
    assert "What was Micron's revenue?" in sent_text
    return FakeResponse()


with patch("generate.retrieve", return_value=fake_chunks), \
     patch("generate.requests.post", side_effect=fake_post):
    result = answer("What was Micron's revenue?")

assert result["answer"] == "Micron's revenue was $37.4 billion."
assert "Revenue was $37.4 billion." in result["context"]
assert result["usage"]["total_tokens"] == 50
assert result["latency"] >= 0
print("ok")
