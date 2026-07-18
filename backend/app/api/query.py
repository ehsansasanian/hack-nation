"""POST /query - natural-language pipeline search (Phase 4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    q: str


@router.post("/query")
def natural_language_query(_: QueryRequest) -> None:
    raise HTTPException(
        status_code=501,
        detail="Natural-language query is implemented in Phase 4 (LLM parse -> filter -> rerank).",
    )
