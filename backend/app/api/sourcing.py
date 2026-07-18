"""POST /sourcing/scan - run the live outbound scanners (Phase 3).

Scanners emit through the shared ingestion pipeline (dedup + entity resolution),
then in-thesis finds are scored via the Phase 2 pipeline and, above threshold,
turned into outbound applications with a draft outreach message. Safe to call
repeatedly: unchanged content dedups to zero new signals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import ScanRequest, ScanSummaryOut
from app.sourcing.service import run_scan

router = APIRouter(tags=["sourcing"])


@router.post("/sourcing/scan", response_model=ScanSummaryOut)
def scan(
    payload: ScanRequest | None = None, session: Session = Depends(get_session)
) -> ScanSummaryOut:
    request = payload or ScanRequest()
    summary = run_scan(session, sources=request.sources, limit=request.limit)
    return ScanSummaryOut.model_validate(summary)