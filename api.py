"""HTTP API over the RAG pipeline: GET /health and POST /ask. Run with: uv run uvicorn api:app --reload"""
from typing import Annotated, Literal

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from embed import is_indexed
from generate import answer

app = FastAPI(title="Filings RAG Assistant")


class AskRequest(BaseModel):
    """Request body for /ask. Bounds on question length, tickers, and top_k cap per-request OpenAI cost."""

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    tickers: list[str] = Field(default=["GOOGL", "MU"], min_length=1, max_length=10)
    method: Literal["vector", "hybrid"] = "vector"
    top_k: int = Field(default=5, ge=1, le=20)


class Chunk(BaseModel):
    """One retrieved filing chunk; `year` is the filing year, stored as a string in Chroma."""

    ticker: str
    year: str
    text: str
    score: float


class AskResponse(BaseModel):
    """Response body for /ask: the answer plus the chunks it was grounded on, token usage, and latency."""

    answer: str
    context: list[Chunk]
    usage: dict
    latency: float


@app.get("/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """Answer a question over already-indexed tickers' filings.

    Plain `def` (not async) so FastAPI runs the blocking OpenAI calls in its threadpool.
    Unknown tickers are rejected up front: ingesting/embedding inside a request would be slow and costly.
    """
    tickers = tuple(dict.fromkeys(t.strip().upper() for t in req.tickers))  # normalize + dedupe, keep order
    missing = [t for t in tickers if not is_indexed(t)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Ticker(s) not indexed: {', '.join(missing)}. Ingest them first.")

    try:
        result = answer(req.question, top_k=req.top_k, method=req.method, tickers=tickers)
    except requests.RequestException:
        # Never echo the exception: it can carry request URLs/headers. Fixed message only.
        raise HTTPException(status_code=502, detail="Upstream model service failed.") from None

    return AskResponse(
        answer=result["answer"],
        context=result["chunks"],
        usage=result["usage"],
        latency=result["latency"],
    )
