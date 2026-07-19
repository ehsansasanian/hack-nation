"""Application endpoints: inbound apply, detail, and memo (later phase)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.ingestion.pipeline import CompanyHint, FounderHint, RawSignal, ingest_signal
from app.models import Application, Memo, RecombinationNote, Signal
from app.sourcing.github import normalize_github_handle
from app.reasoning.analysis import acquire, run_analysis_task
from app.reasoning.diligence import DiligenceOutcome, run_diligence
from app.reasoning.edge import LatestSignal, edge_from_orm
from app.reasoning.memo import generate_memo
from app.reasoning.recombination import RecombinationResult, generate_recombination
from app.reasoning.service import ScoringOutcome, score_application
from app.reasoning.trace import Trace, build_trace
from app.schemas import (
    AnalyzeOut,
    ApplicationCreate,
    ApplicationDetailOut,
    ApplicationOut,
    ClaimOut,
    CompanyOut,
    DiligenceResultOut,
    EdgeLineOut,
    EdgeOut,
    FounderOut,
    MemoOut,
    RecombinationOut,
    ScoreOut,
    ScoringResultOut,
    ThesisFitOut,
    TraceOut,
    TraceSignalOut,
    TraceStepOut,
)

router = APIRouter(tags=["applications"])


def _normalize_declared_links(payload: ApplicationCreate) -> list[dict]:
    """Normalise per-founder self-declared links; fall back to the flat founder_name.

    The ``enriching`` stage consumes this list. Backward compatible: a legacy payload
    with only ``founder_name`` yields a single link-less record (nothing to fetch).
    """
    records: list[dict] = []
    for f in payload.founders:
        rec = {
            "name": f.name,
            "github": (f.github or "").strip() or None,
            "linkedin": (f.linkedin or "").strip() or None,
            "website": (f.website or "").strip() or None,
            "x": (f.x or "").strip() or None,
            "other_links": [link for link in (f.other_links or []) if link],
        }
        if any(rec[k] for k in ("name", "github", "linkedin", "website", "x")) or rec["other_links"]:
            records.append(rec)
    if not records and payload.founder_name:
        records.append(
            {"name": payload.founder_name, "github": None, "linkedin": None,
             "website": None, "x": None, "other_links": []}
        )
    return records


def _primary_founder_hint(records: list[dict]) -> FounderHint | None:
    """Founder hint for the deck signal, carrying the primary founder's declared links."""
    if not records:
        return None
    primary = records[0]
    links = {
        key: primary[key]
        for key in ("github", "linkedin", "website", "x")
        if primary.get(key)
    }
    hint = FounderHint(
        name=primary.get("name"),
        github_handle=normalize_github_handle(primary.get("github")),
        links=links,
    )
    return hint if (hint.name or hint.github_handle) else None


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
    payload: ApplicationCreate,
    background_tasks: BackgroundTasks,
    auto_analyze: bool = True,
    session: Session = Depends(get_session),
) -> Application:
    """Inbound apply: resolve/create the company via the shared ingestion pipeline,
    then attach (idempotently) an inbound Application carrying the deck text.

    When ``auto_analyze`` (default ``true``) the full reasoning chain - screening,
    scoring, diligence, memo - is scheduled in the background; the response returns
    immediately with ``analysis_status='received'`` and the caller polls
    ``GET /applications/{id}`` to watch it progress.
    """
    declared_links = _normalize_declared_links(payload)
    raw = RawSignal(
        source="deck",
        content={"kind": "inbound_application", "deck_text": payload.deck_text or ""},
        timestamp=datetime.now(UTC),
        founder=_primary_founder_hint(declared_links),
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
            declared_links=declared_links,
        )
        session.add(application)
    else:
        if payload.deck_text:
            application.deck_text = payload.deck_text
        if declared_links:  # a re-apply may add/replace the self-declared links
            application.declared_links = declared_links

    session.commit()
    session.refresh(application)

    if auto_analyze and acquire(application.id):
        application.analysis_status = "received"
        application.analysis_error = None
        session.commit()
        session.refresh(application)
        background_tasks.add_task(run_analysis_task, application.id)

    return application


@router.post("/applications/{application_id}/analyze", response_model=AnalyzeOut)
def analyze_application_endpoint(
    application_id: int,
    background_tasks: BackgroundTasks,
    force: bool = False,
    session: Session = Depends(get_session),
) -> AnalyzeOut:
    """Manually (re)run the auto-analysis chain for one application.

    Idempotent and guarded: if a run is already in flight this is a no-op
    (``scheduled=false``). A completed (``ready``) application is not re-run unless
    ``force=true``. Otherwise the chain is scheduled in the background and the
    caller polls ``GET /applications/{id}``.

    The in-flight guard is in-process only (a module-level set) - correct for the
    single-process demo, but it would not coordinate across multiple workers.
    """
    app = session.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found.")

    if app.analysis_status == "ready" and not force:
        return AnalyzeOut(
            application_id=application_id,
            analysis_status=app.analysis_status,
            scheduled=False,
            detail="Already analysed; pass force=true to re-run.",
        )

    if not acquire(application_id):
        return AnalyzeOut(
            application_id=application_id,
            analysis_status=app.analysis_status,
            scheduled=False,
            detail="Analysis already in flight.",
        )

    app.analysis_status = "received"
    app.analysis_error = None
    session.commit()
    background_tasks.add_task(run_analysis_task, application_id)
    return AnalyzeOut(
        application_id=application_id,
        analysis_status="received",
        scheduled=True,
        detail="Analysis scheduled.",
    )


def _latest_signal(session: Session, application: Application) -> LatestSignal | None:
    """The freshest evidence signal for the application's company + its founders.

    Feeds the Edge panel's signal-recency line. Read-only; None when there are no
    datable signals to cite.
    """
    founder_ids = [f.id for f in application.company.founders]
    conds = [Signal.company_id == application.company.id]
    if founder_ids:
        conds.append(Signal.founder_id.in_(founder_ids))
    sig = session.scalar(
        select(Signal).where(or_(*conds)).order_by(Signal.timestamp.desc()).limit(1)
    )
    if sig is None:
        return None
    return LatestSignal(id=sig.id, source=sig.source, timestamp=sig.timestamp)


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
    # Server-computed, deterministic "why is this alpha" read (qualitative only).
    edge = edge_from_orm(application, _latest_signal(session, application))
    detail.edge = EdgeOut(
        summary=edge.summary,
        has_edge=edge.has_edge,
        lines=[EdgeLineOut(**asdict(line)) for line in edge.lines],
    )
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


@router.post("/applications/{application_id}/memo", response_model=MemoOut)
def generate_memo_endpoint(
    application_id: int,
    backend: str | None = None,
    session: Session = Depends(get_session),
) -> Memo:
    """Generate (or regenerate) the investment memo for one application.

    Runs diligence first if it has not run yet, writes the five required sections
    with every claim rendered at its trust level, explicit gap flags, and a
    recommendation tied to thesis fit and the three axis scores. Upserts the memo.
    """
    try:
        generate_memo(session, application_id, prefer_backend=backend)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    memo = session.scalar(select(Memo).where(Memo.application_id == application_id))
    if memo is None:  # pragma: no cover - generate_memo always upserts one
        raise HTTPException(status_code=500, detail="Memo generation produced no memo.")
    return memo


def _to_trace_out(trace: Trace) -> TraceOut:
    return TraceOut(
        application_id=trace.application_id,
        company=CompanyOut.model_validate(trace.company),
        backend=trace.backend,
        memo_recommendation=trace.memo_recommendation,
        signals=[TraceSignalOut.model_validate(s) for s in trace.signals],
        steps=[TraceStepOut.model_validate(s) for s in trace.steps],
    )


@router.get("/applications/{application_id}/trace", response_model=TraceOut)
def get_application_trace(
    application_id: int, session: Session = Depends(get_session)
) -> TraceOut:
    """Phase 6 traceability: the full reasoning chain for one application.

    Ordered steps - signals ingested -> screening -> per-axis scoring -> claims +
    truth-gap -> memo - assembled from existing rows (no separate trace log), each
    pointing back at the exact signal ids it reasoned over. The resolved signal
    dossier is returned alongside so the "Why?" panel can render each cited
    signal's source, timestamp and excerpt without further calls.
    """
    try:
        trace = build_trace(session, application_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_trace_out(trace)


@router.get("/applications/{application_id}/memo", response_model=MemoOut)
def get_memo(application_id: int, session: Session = Depends(get_session)) -> Memo:
    memo = session.scalar(select(Memo).where(Memo.application_id == application_id))
    if memo is None:
        raise HTTPException(
            status_code=404,
            detail="No memo yet. POST /applications/{id}/memo to generate one.",
        )
    return memo


def _to_recombination_out(result: RecombinationResult) -> RecombinationOut:
    return RecombinationOut(
        application_id=result.application_id,
        company=result.company,
        standing=result.standing,
        weak_axes=result.weak_axes,
        gaps=result.gaps,
        candidates=[asdict(c) for c in result.candidates],
        idea_pivots=result.idea_pivots,
        contingent_note=result.contingent_note,
        reeval_weeks=result.reeval_weeks,
        backend=result.backend,
    )


@router.post("/applications/{application_id}/recombine", response_model=RecombinationOut)
def recombine_application(
    application_id: int,
    backend: str | None = None,
    session: Session = Depends(get_session),
) -> RecombinationOut:
    """Co-founder & idea recombination for a low-scoring application (HYPOTHETICAL).

    Reads the weak axes/gaps, shortlists complementary founders from Memory
    (skill/domain fit + availability = not tied to an active in-thesis deal),
    suggests idea pivots and emits a clearly-labeled contingent IC note. Real axis
    scores are never mutated. ``backend`` may pin ``openai`` or ``offline``; the
    candidate shortlist is deterministic on both paths, only the note narrative
    differs. Upserts the note (a re-run replaces, never duplicates).
    """
    try:
        result = generate_recombination(session, application_id, prefer_backend=backend)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_recombination_out(result)


@router.get("/applications/{application_id}/recombination", response_model=RecombinationOut)
def get_recombination(
    application_id: int, session: Session = Depends(get_session)
) -> RecombinationOut:
    """Fetch the stored recombination note, or 404 if one has not been generated."""
    note = session.scalar(
        select(RecombinationNote).where(RecombinationNote.application_id == application_id)
    )
    if note is None:
        raise HTTPException(
            status_code=404,
            detail="No recombination note yet. POST /applications/{id}/recombine to generate one.",
        )
    app = session.get(
        Application, application_id, options=[selectinload(Application.company)]
    )
    return RecombinationOut(
        application_id=note.application_id,
        company=app.company.name if app else "",
        standing=note.standing or "",
        weak_axes=note.weak_axes or [],
        gaps=note.gaps or [],
        candidates=note.candidates or [],
        idea_pivots=note.idea_pivots or [],
        contingent_note=note.contingent_note or "",
        reeval_weeks=note.reeval_weeks or 8,
        backend=note.backend or "offline-deterministic",
    )
