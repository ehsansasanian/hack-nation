"""Application endpoints: inbound apply, detail, and memo (later phase)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.ingestion.pipeline import CompanyHint, FounderHint, RawSignal, ingest_signal
from app.models import Application
from app.schemas import (
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    FounderOut,
)

router = APIRouter(tags=["applications"])


@router.post("/applications", response_model=ApplicationOut, status_code=201)
def create_application(
    payload: ApplicationCreate, session: Session = Depends(get_session)
) -> Application:
    """Inbound apply: resolve/create the company via the shared ingestion pipeline,
    then attach (idempotently) an inbound Application carrying the deck text."""
    raw = RawSignal(
        source="deck",
        content={"kind": "inbound_application", "deck_text": payload.deck_text or ""},
        timestamp=datetime.now(UTC),
        founder=FounderHint(name=payload.founder_name) if payload.founder_name else None,
        company=CompanyHint(
            name=payload.company_name,
            sector=payload.sector,
            stage=payload.stage,
            geography=payload.geography,
            one_liner=payload.one_liner,
        ),
    )
    signal, _ = ingest_signal(session, raw)
    if signal.company_id is None:
        raise HTTPException(status_code=400, detail="Could not resolve a company from the payload.")

    application = session.scalar(
        select(Application).where(
            Application.company_id == signal.company_id,
            Application.origin == "inbound",
        )
    )
    if application is None:
        application = Application(
            company_id=signal.company_id,
            deck_text=payload.deck_text,
            origin="inbound",
            status="in_review",
        )
        session.add(application)
    elif payload.deck_text:
        application.deck_text = payload.deck_text

    session.commit()
    session.refresh(application)
    return application


@router.get("/applications/{application_id}", response_model=ApplicationDetailOut)
def get_application(
    application_id: int, session: Session = Depends(get_session)
) -> ApplicationDetailOut:
    application = session.get(
        Application,
        application_id,
        options=[
            selectinload(Application.company),
            selectinload(Application.scores),
            selectinload(Application.claims),
        ],
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    detail = ApplicationDetailOut.model_validate(application)
    detail.founders = [FounderOut.model_validate(f) for f in application.company.founders]
    return detail


@router.get("/applications/{application_id}/memo")
def get_memo(application_id: int) -> None:
    raise HTTPException(
        status_code=501,
        detail="Memo generation is implemented in Phase 4 (diligence, trust score & memo).",
    )
