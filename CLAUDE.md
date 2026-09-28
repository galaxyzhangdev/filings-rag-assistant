# Project: Filings RAG Assistant

## What this is
A personal portfolio project: a RAG (retrieval-augmented generation) Q&A
system over public company SEC filings. Built to demonstrate RAG +
evaluation skills for a Data Engineer -> AI Engineer job transition.

Framed honestly as a personal project motivated by starting to learn
investing — NOT a work project, no employer data, no confidential
information of any kind.

## Companies
- **Ingestion is generic**: the pipeline looks up any public company by
  ticker via SEC EDGAR and fetches its filings. Do not hardcode a fixed
  list of companies in the ingestion code.
- **Evaluation is fixed to 2 companies**: Alphabet (GOOGL) and Micron (MU).
  The hand-written eval set and all reported metrics are based on these two.
- For each company, fetch the **latest 2 years of 10-K filings** (not just
  the most recent one), so multi-hop eval questions can compare both across
  companies and year-over-year within one company.

Data source: SEC EDGAR public API. No API key required, only a
`User-Agent` header per SEC's usage policy.

## Scope — CORE ONLY, build in this order

Only build what's listed below. Do not add features from the "Explicitly
out of scope for now" section unless asked.

1. **Company/filing lookup**: given a ticker, resolve it to a CIK using
   SEC's `company_tickers.json`, then query the submissions API
   (`data.sec.gov/submissions/CIK##########.json`) to find the latest 2
   `10-K` filings and their document URLs.
2. **Ingestion**: download each filing, parse the HTML with
   `beautifulsoup4` to extract clean text, chunk it (~500 tokens via
   `tiktoken`, with some overlap), and save chunks with metadata (ticker,
   filing year, chunk text) to a local file.
   - Cache by ticker: if a company's filings are already downloaded and
     chunked, don't re-fetch or re-process them.
3. **Embedding**: embed each chunk using GitHub Models'
   `text-embedding-3-small` (same `GITHUB_TOKEN` used for chat). Store
   embeddings alongside the chunks (local `.json`/`.npy` file — no vector
   database).
4. **Retrieval**: vector search only — embed the question, compute cosine
   similarity against all stored chunk embeddings via `numpy`, take the
   top-k highest-scoring chunks. No BM25, no hybrid retrieval for now.
5. **Generation**: take the user's question, retrieve top-k chunks, stuff
   them into a prompt, call `gpt-4.1-mini` (via GitHub Models) for the
   answer.
6. **Evaluation** (on Alphabet + Micron only):
   - Build a ~15-20 question eval set: factual (e.g. "what was GOOGL's
     revenue in [year]"), multi-hop (both cross-company — "which had
     higher revenue, GOOGL or MU" — and cross-year — "how did GOOGL's
     revenue change year over year"), and should-abstain (asking about
     things not in the filings).
   - Score answers with the RAG triad: context relevance, groundedness,
     answer relevance. Use **Arize Phoenix** for this.
   - Track token cost and latency per question (basic — print/log per
     call, no need for formal p95 statistics at this stage).

## Explicitly out of scope for now (do not build unless asked)
- Hybrid retrieval (BM25 keyword search combined with vector search).
- Reranker (cross-encoder re-ranking of retrieved chunks).
- Judge calibration against hand-labeled data.
- Deployment: FastAPI endpoint, Docker packaging. NOT being built in this
  project phase at all — do not scaffold this.

## Rate limit awareness
GitHub Models' free tier caps low-complexity models (the embedding and
chat models used here) at ~150 requests/day, 15/minute. This matters
because ingestion + evaluation can add up quickly:
- Cache embeddings and chunks (see step 2) so nothing is re-embedded.
- Cache LLM answers per (question, retrieval method) pair during
  evaluation so re-running the eval script doesn't re-call the API for
  unchanged inputs.
- When testing/debugging, prefer re-running against cached data over
  re-triggering live API calls.

## Tech stack
- Python 3.12, `uv` for environment/dependency management.
- `requests` + `beautifulsoup4` for fetching and parsing SEC filings.
- `tiktoken` for token-based chunking and cost tracking.
- LLM + embeddings via GitHub Models (`GITHUB_TOKEN` env var):
  - Chat: `gpt-4.1-mini`
  - Embeddings: `text-embedding-3-small`
- Retrieval: `numpy` (cosine similarity) only, no vector database.
- Evaluation: Arize Phoenix.

## Code style
- Every function/code block needs a concise, professional English
  comment stating exactly what that block does — not a tutorial, just
  clear and accurate. No filler comments, no restating obvious code
  line-by-line.
- Keep implementations minimal and simple (this project also uses the
  `ponytail` plugin, which pushes toward the smallest working solution —
  follow that instinct: stdlib/simple libraries first, no unnecessary
  abstraction layers, no framework unless the scope above calls for one).
- I'm getting back into coding after a long break — prefer straightforward,
  readable code over clever one-liners.

## Working style
- Build ONE step from the Scope list at a time. After finishing a step,
  briefly explain what was built before moving to the next step.
- Do not jump ahead to later steps or add out-of-scope features without
  asking first.
