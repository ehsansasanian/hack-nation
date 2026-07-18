"""POST /sourcing/scan - trigger outbound GitHub/HN sourcing (Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["sourcing"])


@router.post("/sourcing/scan")
def scan() -> None:
    raise HTTPException(
        status_code=501,
        detail="Outbound sourcing scanners are implemented in Phase 3 (GitHub/HN via the shared pipeline).",
    )
