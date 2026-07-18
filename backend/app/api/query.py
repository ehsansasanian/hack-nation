"""POST /query - natural-language pipeline search (Phase 4).

Parses a compound query into structured filters (LLM with offline fallback),
hard-filters the pipeline, and returns the survivors reranked with a per-result
match rationale.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.reasoning.query import QueryResult, run_query

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    q: str
    backend: str | None = None  # pin 'openai' / 'offline'; default auto with fallback


class ParsedQueryOut(BaseModel):
    sector: str = ""
    geography: str = ""
    stage: str = ""
    attributes: list[str] = []


class QueryMatchOut(BaseModel):
    application_id: int
    company: str
    sector: str | None = None
    geography: str | None = None
    stage: str | None = None
    scores: dict[str, float] = {}
    match_score: float
    partial: bool
    rationale: str


class QueryResponse(BaseModel):
    query: str
    backend: str
    parsed: ParsedQueryOut
    results: list[QueryMatchOut] = []


def _to_response(result: QueryResult) -> QueryResponse:
    return QueryResponse(
        query=result.query,
        backend=result.backend if result.fallback_from is None
        else f"{result.backend} (fallback from {result.fallback_from})",
        parsed=ParsedQueryOut(
            sector=result.parsed.sector,
            geography=result.parsed.geography,
            stage=result.parsed.stage,
            attributes=result.parsed.attributes,
        ),
        results=[
            QueryMatchOut(
                application_id=m.application_id, company=m.company, sector=m.sector,
                geography=m.geography, stage=m.stage, scores=m.scores,
                match_score=m.match_score, partial=m.partial, rationale=m.rationale,
            )
            for m in result.results
        ],
    )


@router.post("/query", response_model=QueryResponse)
def natural_language_query(
    payload: QueryRequest, session: Session = Depends(get_session)
) -> QueryResponse:
    result = run_query(session, payload.q, prefer_backend=payload.backend)
    return _to_response(result)
