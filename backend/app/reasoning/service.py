"""Phase 2 orchestrator: thesis filter -> screening -> 3-axis scoring.

``score_application`` is the single entry point the API and the CLI both call.
Order of operations:

1. Hard thesis filter (deterministic). Out of scope -> screened_out, unless forced.
2. Screening (cheap model). Non-viable -> screened_out, unless forced.
3. Three independent axis scores (founder / market / idea_vs_market). The founder
   axis switches to the cold-start rubric when the founder has no track record.
4. Persistent Founder Score update for every founder on the company.

The axes are never averaged. Evidence ids returned by a backend are validated
against the per-axis universe; hallucinated ids are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Company, Score, Thesis
from app.reasoning.backend import ReasoningBackend, get_backend
from app.reasoning.context import ScoringContext, build_context
from app.reasoning.founder_score import update_founder_score
from app.reasoning.schemas import AxisResult, ColdStartAxisResult
from app.reasoning.thesis_fit import ThesisFit, thesis_fit

AXES = ("founder", "market", "idea_vs_market")


@dataclass(slots=True)
class ScoringOutcome:
    application_id: int
    status: str
    backend: str
    thesis_fit: ThesisFit
    screening_verdict: str | None
    screening_rationale: str | None
    cold_start: bool
    scores: list[Score] = field(default_factory=list)
    forced: bool = False
    fallback_from: str | None = None


def _active_thesis(session: Session) -> Thesis | None:
    return session.scalar(select(Thesis).order_by(Thesis.id.desc()))


def _load_application(session: Session, application_id: int) -> Application:
    app = session.get(
        Application,
        application_id,
        options=[
            selectinload(Application.company).selectinload(Company.founders),
            selectinload(Application.scores),
        ],
    )
    if app is None:
        raise LookupError(f"Application {application_id} not found.")
    return app


def _upsert_score(session: Session, application_id: int, axis: str, **fields) -> Score:
    existing = session.scalar(
        select(Score).where(Score.application_id == application_id, Score.axis == axis)
    )
    if existing is None:
        existing = Score(application_id=application_id, axis=axis)
        session.add(existing)
    for key, value in fields.items():
        setattr(existing, key, value)
    return existing


def _validate_evidence(returned: list[int], universe: set[int]) -> list[int]:
    """Keep only cited ids that were actually shown to the model."""
    return [i for i in dict.fromkeys(returned) if i in universe]


def score_application(
    session: Session,
    application_id: int,
    force: bool = False,
    prefer_backend: str | None = None,
    allow_fallback: bool = True,
) -> ScoringOutcome:
    app = _load_application(session, application_id)
    thesis = _active_thesis(session)
    fit = thesis_fit(app.company, thesis)

    # 1. Hard thesis filter.
    if not fit.in_scope and not force:
        app.screening_verdict = "thesis_mismatch"
        app.screening_rationale = fit.rationale
        app.status = "screened_out"
        session.commit()
        return ScoringOutcome(
            application_id=app.id,
            status=app.status,
            backend="thesis-filter",
            thesis_fit=fit,
            screening_verdict=app.screening_verdict,
            screening_rationale=app.screening_rationale,
            cold_start=False,
        )

    backend = get_backend(prefer_backend)
    try:
        return _run_scoring(session, app, fit, backend, force)
    except OpenAIError as exc:
        if not (allow_fallback and backend.name != "offline-deterministic"):
            raise
        session.rollback()
        app = _load_application(session, application_id)
        fit = thesis_fit(app.company, _active_thesis(session))
        offline = get_backend("offline")
        outcome = _run_scoring(session, app, fit, offline, force)
        outcome.fallback_from = f"openai ({type(exc).__name__})"
        return outcome


def _run_scoring(
    session: Session,
    app: Application,
    fit: ThesisFit,
    backend: ReasoningBackend,
    force: bool,
) -> ScoringOutcome:
    ctx = build_context(session, app, fit.rationale)

    # 2. Screening.
    verdict = backend.screen(ctx)
    app.screening_verdict = "viable" if verdict.viable else "non_viable"
    app.screening_rationale = verdict.reason

    if not verdict.viable and not force:
        app.status = "screened_out"
        session.commit()
        return ScoringOutcome(
            application_id=app.id,
            status=app.status,
            backend=backend.name,
            thesis_fit=fit,
            screening_verdict=app.screening_verdict,
            screening_rationale=app.screening_rationale,
            cold_start=ctx.cold_start,
        )

    # 3. Three independent axes.
    scores: list[Score] = []
    founder_result, founder_evidence_score, founder_conf = _score_founder(session, app, ctx, backend)
    scores.append(founder_result)
    scores.append(_score_generic(session, app, ctx, backend, "market"))
    scores.append(_score_generic(session, app, ctx, backend, "idea_vs_market"))

    # 4. Persistent Founder Score update (all founders on the company).
    founder_trend = "stable"
    for founder in ctx.founders:
        _, founder_trend = update_founder_score(
            founder,
            evidence_score=founder_evidence_score,
            confidence=founder_conf,
            cold_start=ctx.cold_start,
            application_id=app.id,
            company_name=app.company.name,
        )
    founder_result.trend = founder_trend  # founder-axis trend comes from persistent history

    app.status = "in_review"
    session.commit()
    for s in scores:
        session.refresh(s)
    return ScoringOutcome(
        application_id=app.id,
        status=app.status,
        backend=backend.name,
        thesis_fit=fit,
        screening_verdict=app.screening_verdict,
        screening_rationale=app.screening_rationale,
        cold_start=ctx.cold_start,
        scores=scores,
        forced=force,
    )


def _score_founder(
    session: Session, app: Application, ctx: ScoringContext, backend: ReasoningBackend
) -> tuple[Score, float, float]:
    """Founder axis, with the cold-start branch. Returns (score, evidence_value, confidence)."""
    universe = ctx.founder_evidence_ids()
    if ctx.cold_start:
        res: ColdStartAxisResult = backend.score_founder_cold_start(ctx)
        low, high = sorted((res.score_low, res.score_high))
        midpoint = round((low + high) / 2, 1)
        score = _upsert_score(
            session,
            app.id,
            "founder",
            value=midpoint,
            trend="stable",
            rationale=res.rationale,
            evidence_signal_ids=_validate_evidence(res.evidence_signal_ids, universe),
            confidence=res.confidence,
            cold_start=True,
            score_low=low,
            score_high=high,
            model=backend.name,
        )
        return score, midpoint, res.confidence

    res_axis: AxisResult = backend.score_founder(ctx)
    score = _upsert_score(
        session,
        app.id,
        "founder",
        value=res_axis.score,
        trend=res_axis.trend,
        rationale=res_axis.rationale,
        evidence_signal_ids=_validate_evidence(res_axis.evidence_signal_ids, universe),
        confidence=res_axis.confidence,
        cold_start=False,
        score_low=None,
        score_high=None,
        model=backend.name,
    )
    return score, res_axis.score, res_axis.confidence


def _score_generic(
    session: Session,
    app: Application,
    ctx: ScoringContext,
    backend: ReasoningBackend,
    axis: str,
) -> Score:
    if axis == "market":
        res = backend.score_market(ctx)
        universe = ctx.market_evidence_ids()
    else:
        res = backend.score_idea(ctx)
        universe = ctx.idea_evidence_ids()
    return _upsert_score(
        session,
        app.id,
        axis,
        value=res.score,
        trend=res.trend,
        rationale=res.rationale,
        evidence_signal_ids=_validate_evidence(res.evidence_signal_ids, universe),
        confidence=res.confidence,
        cold_start=False,
        score_low=None,
        score_high=None,
        model=backend.name,
    )
