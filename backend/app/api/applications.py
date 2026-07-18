"""Application endpoints: inbound apply, detail, and memo (later phase)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.ingestion.pipeline import CompanyHint, FounderHint, RawSignal, ingest_signal
from app.models import Application
from app.reasoning.diligence import DiligenceOutcome, run_diligence
from app.reasoning.service import ScoringOutcome, score_application
from app.schemas import (
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    ClaimOut,
    DiligenceResultOut,
    FounderOut,
    ScoreOut,
    ScoringResultOut,
    ThesisFitOut,
)

router = APIRouter(tags=["applications"])


def _to_scoring_result(outcome: ScoringOutcome) -> ScoringResultOut:
    return ScoringResultOut(
        application_id=outcome.application_id,
        status=outcome.status,
        backend=outcome.backend if outcome.fallback_from is None
        else f"{outcome.backend} (fallback from {outcome.fallback_from})",
        thesis_fit=ThesisFitOut(
            in_scope=outcome.thesis_fit.in_scope,
            out_of_scope_reasons=outcome.thesis_fit.out_of_scope_reasons,
            rationale=outcome.thesis_fit.rationale,
        ),
        screening_verdict=outcome.screening_verdict,
        screening_rationale=outcome.screening_rationale,
        cold_start=outcome.cold_start,
        scores=[ScoreOut.model_validate(s) for s in outcome.scores],
    )


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


@router.post("/applications/{application_id}/score", response_model=ScoringResultOut)
def score_application_endpoint(
    application_id: int,
    force: bool = False,
    backend: str | None = None,
    session: Session = Depends(get_session),
) -> ScoringResultOut:
    """Run the Phase 2 reasoning pipeline for one application.

    thesis filter -> screening -> 3 independent axis scores (+ cold-start branch)
    -> persistent Founder Score update. ``force=true`` scores even when the app is
    screened out or out of thesis scope (analyst override). ``backend`` may pin
    ``openai`` or ``offline``; by default a live-call failure falls back to offline.
    """
    try:
        outcome = score_application(session, application_id, force=force, prefer_backend=backend)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_scoring_result(outcome)


def _to_diligence_result(outcome: DiligenceOutcome) -> DiligenceResultOut:
    return DiligenceResultOut(
        application_id=outcome.application_id,
        backend=outcome.backend if outcome.fallback_from is None
        else f"{outcome.backend} (fallback from {outcome.fallback_from})",
        n_claims=len(outcome.claims),
        n_contradicted=outcome.n_contradicted,
        n_verified=outcome.n_verified,
        unsupported_axes=outcome.unsupported_axes,
        claims=[ClaimOut.model_validate(c) for c in outcome.claims],
    )


@router.post("/applications/{application_id}/diligence", response_model=DiligenceResultOut)
def run_diligence_endpoint(
    application_id: int,
    backend: str | None = None,
    session: Session = Depends(get_session),
) -> DiligenceResultOut:
    """Run the Phase 4 diligence pipeline for one application.

    claim extraction -> per-claim truth-gap against stored signals -> validator
    self-correction. Claims are upserted (a re-run never duplicates them).
    ``backend`` may pin ``openai`` or ``offline``; a live-call failure falls back
    to offline. Scoring should have run first so the validator can refute axes.
    """
    try:
        outcome = run_diligence(session, application_id, prefer_backend=backend)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_diligence_result(outcome)
