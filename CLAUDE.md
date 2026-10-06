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
3. **Embedding**: embed each chunk using OpenAI's `text-embedding-3-small`
   (same `OPENAI_API_KEY` used for chat). Store embeddings in **Chroma**, a
   local embedded vector database (no server), persisted to disk.
4. **Retrieval**: vector search only — embed the question, query Chroma for
   the top-k most similar chunks per ticker, and merge results across
   tickers. Vector is the default; an optional `method="hybrid"`
   (BM25 + vector, fused with RRF) was added later (see NOTES.md Step 7).
5. **Generation**: take the user's question, retrieve top-k chunks, stuff
   them into a prompt, call OpenAI's `gpt-4.1-mini` for the answer.
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
- Reranker (cross-encoder re-ranking of retrieved chunks).
- Judge calibration against hand-labeled data.
- Deployment: Docker packaging. NOT being built in this project phase at
  all — do not scaffold this. (A local FastAPI service, `api.py`, was added
  later — see NOTES.md Step 8.)

## Rate limit awareness
OpenAI's API is billed per token, and both ingestion and evaluation can add
up to a meaningful number of calls quickly. Keep cost and request volume
under control:
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
- LLM + embeddings via OpenAI API (`OPENAI_API_KEY` env var):
  - Chat: `gpt-4.1-mini`
  - Embeddings: `text-embedding-3-small`
- Retrieval: `chromadb` (local embedded vector database, persisted to
  disk, no server).
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

## Learning notes (bilingual glossary + step flow)
I'm new to these terms and libraries, so after finishing each step of the
Scope list, append to a file called `NOTES.md` in the project root (create
it if it doesn't exist) with an entry for that step. Each entry has TWO
parts, in this order:

1. **How this step works** — grouped by file and function, so I can find
   the matching code while reading. For each function involved in this
   step, add a `` **`file.py` -> `function_name(params)`** `` header,
   followed by a short numbered list of what that function does, start
   to finish (input -> ... -> output). This is about control flow/logic,
   not term definitions. Each numbered item is bilingual: one
   plain-English line, then an indented Chinese line under it. If a step
   involves more than one function, add one header block per function,
   in the order they're called.
2. **Terms glossary** — the bilingual glossary of new terms/functions/
   concepts introduced, same format as before.

Format per entry:

```
## Step N: <short step name>

### How this step works

**`<file>.py` -> `<function_name>(<params>)`**
1. <plain-English description of the first operation>
   > 中文：<对应中文描述>
2. <plain-English description of the next operation>
   > 中文：<对应中文描述>
...

**`<file>.py` -> `<next_function_name>(<params>)`**  (only if a second function is involved)
1. ...

### Terms
- **<English term>** — <one-line English explanation>
  > 中文：<2-3 句中文解释，说明是什么、为什么这么做>
```

One glossary entry per new term or function worth knowing (not every
single line of code — just the concepts/APIs/libraries that are new or
non-obvious). Keep each explanation short and plain, no jargon left
unexplained. This file is for me to study from, not part of the shipped
project logic.

## Interview notes
After finishing each step (same time as the NOTES.md update), also append
an entry to a separate file called `INTERVIEW_NOTES.md` in the project
root (create it if it doesn't exist). This is prep material for talking
about the project out loud in an interview — separate from NOTES.md,
which is for learning the concepts. Format per entry:

```
## Step N: <short step name>

**What I built**: 1-2 plain sentences, no jargon dump, describing what
this step does.
**Why this approach**: why this choice was made over alternatives —
show judgment, not "the tutorial said so."
**Trade-off / limitation**: current limitation of this approach, and
what I'd improve with more time.
**If they push**: one likely follow-up question an interviewer might
ask about this step, plus a short answer.
```

Keep every field short (1-3 sentences max) and in plain spoken language —
this should read like something I'd actually say out loud, not a written
report.
