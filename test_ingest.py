"""Self-check: text extraction and chunking work correctly, with no network calls."""
from ingest import chunk_text, extract_text, ENCODING

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

print("ok")
