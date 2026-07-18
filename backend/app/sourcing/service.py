"""Outbound sourcing orchestrator: scan -> ingest -> converge into the funnel.

One entry point, ``run_scan``:

1. Run the requested live scanners (GitHub / HN / arXiv). A source that fails
   (network / rate limit) is recorded and skipped - the scan still returns.
2. Push every ``RawSignal`` through the *shared* ingestion pipeline, so dedup and
   entity resolution are identical to inbound + synthetic. Re-runs create zero
   duplicate signals for unchanged content (dedup keys are stable ids).
3. Convergence: for each in-thesis company touched by this scan, create (or
   reuse) an ``Application(origin="outbound")`` and score it through the exact
   Phase 2 pipeline (auto-falling back to the offline backend). Candidates that
   clear the score threshold get a personalized draft outreach message.

The result summary is safe to surface on the "Scan" button and to re-run live.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.pipeline import RawSignal, ingest_signal
from app.models import Application, Company, Founder, Score, Signal, Thesis
from app.reasoning.service import score_application
from app.reasoning.thesis_fit import thesis_fit
from app.sourcing.client import SourcingError
from app.sourcing.github import scan_github
from app.sourcing.hn import scan_hn
from app.sourcing.outreach import draft_outreach

# A candidate must reach this on its strongest axis to warrant a draft outreach.
OUTREACH_SCORE_THRESHOLD = 5.5

# source name -> scanner callable(limit) -> list[RawSignal]
SCANNERS: dict[str, Callable[..., list[RawSignal]]] = {
    "github": scan_github,
    "hn": scan_hn,
}
DEFAULT_SOURCES = ("github", "hn")


@dataclass(slots=True)
class CandidateResult:
    source: str
    handle: str
    company: str
    why_flagged: str
    status: str  # in_review / screened_out / out_of_thesis
    application_id: int | None = None
    best_axis: str | None = None
    best_score: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    outreach_drafted: bool = False


@dataclass(slots=True)
class ScanSummary:
    sources_requested: list[str]
    source_errors: dict[str, str] = field(default_factory=dict)
    signals_fetched: int = 0
    signals_created: int = 0
    signals_duplicate: int = 0
    founders_created: int = 0
    companies_created: int = 0
    applications_created: int = 0
    outbound_in_review: int = 0
    outbound_screened_out: int = 0
    outreach_drafts: int = 0
    candidates: list[CandidateResult] = field(default_factory=list)


def _counts(session: Session) -> tuple[int, int, int]:
    return (
        session.scalar(select(func.count()).select_from(Founder)) or 0,
        session.scalar(select(func.count()).select_from(Company)) or 0,
        session.scalar(select(func.count()).select_from(Application)) or 0,
    )


def _active_thesis(session: Session) -> Thesis | None:
    return session.scalar(select(Thesis).order_by(Thesis.id.desc()))


def run_scan(
    session: Session,
    sources: list[str] | None = None,
    limit: int = 10,
) -> ScanSummary:
    requested = [s for s in (sources or DEFAULT_SOURCES) if s in SCANNERS]
    summary = ScanSummary(sources_requested=requested)
    founders_before, companies_before, apps_before = _counts(session)

    # 1 + 2. Scan each source and ingest through the shared pipeline.
    touched_company_ids: set[int] = set()
    for source in requested:
        try:
            raw_signals = SCANNERS[source](limit=limit)
        except SourcingError as exc:
            summary.source_errors[source] = str(exc)
            continue
        summary.signals_fetched += len(raw_signals)
        for raw in raw_signals:
            signal, created = ingest_signal(session, raw)
            summary.signals_created += int(created)
            summary.signals_duplicate += int(not created)
            if signal.company_id is not None:
                touched_company_ids.add(signal.company_id)
    session.commit()

    # 3. Convergence.
    thesis = _active_thesis(session)
    for company_id in touched_company_ids:
        result = _converge_company(session, company_id, thesis)
        if result is not None:
            summary.candidates.append(result)

    founders_after, companies_after, apps_after = _counts(session)
    summary.founders_created = founders_after - founders_before
    summary.companies_created = companies_after - companies_before
    summary.applications_created = apps_after - apps_before
    summary.outbound_in_review = sum(c.status == "in_review" for c in summary.candidates)
    summary.outbound_screened_out = sum(c.status == "screened_out" for c in summary.candidates)
    summary.outreach_drafts = sum(c.outreach_drafted for c in summary.candidates)
    # Strongest candidates first for the demo.
    summary.candidates.sort(key=lambda c: (c.best_score or -1), reverse=True)
    return summary


def _converge_company(
    session: Session, company_id: int, thesis: Thesis | None
) -> CandidateResult | None:
    company = session.get(Company, company_id)
    if company is None:
        return None
    signals = list(session.scalars(select(Signal).where(Signal.company_id == company_id)).all())
    source, handle, why = _provenance(company, signals)

    fit = thesis_fit(company, thesis)
    if not fit.in_scope:
        return CandidateResult(
            source=source, handle=handle, company=company.name,
            why_flagged=why, status="out_of_thesis",
        )

    application, created = _get_or_create_outbound_app(session, company_id)

    # Score only a freshly-created app. Re-scans are then a true no-op: no new
    # signals, no re-scoring, no drift of the persistent Founder Score. An analyst
    # can always re-score deliberately via POST /applications/{id}/score.
    if created:
        outcome = score_application(session, application.id)
        status = outcome.status
        scores = {s.axis: s.value for s in outcome.scores}
    else:
        status = application.status
        scores = {
            s.axis: s.value
            for s in session.scalars(select(Score).where(Score.application_id == application.id))
        }

    best_axis, best_score = _best_axis(scores)
    result = CandidateResult(
        source=source, handle=handle, company=company.name, why_flagged=why,
        status=status, application_id=application.id,
        best_axis=best_axis, best_score=best_score, scores=scores,
        outreach_drafted=application.outreach_draft is not None,
    )

    if (
        created
        and status == "in_review"
        and best_score is not None
        and best_score >= OUTREACH_SCORE_THRESHOLD
    ):
        founder = company.founders[0] if company.founders else None
        if founder is not None:
            application.outreach_draft = draft_outreach(
                founder, company, signals, thesis, best_axis or "founder", best_score
            )
            session.commit()
            result.outreach_drafted = True
    return result


def _get_or_create_outbound_app(session: Session, company_id: int) -> tuple[Application, bool]:
    application = session.scalar(
        select(Application).where(
            Application.company_id == company_id, Application.origin == "outbound"
        )
    )
    if application is not None:
        return application, False
    application = Application(company_id=company_id, origin="outbound", status="in_review")
    session.add(application)
    session.commit()
    session.refresh(application)
    return application, True


def _provenance(company: Company, signals: list[Signal]) -> tuple[str, str, str]:
    """Derive the primary source, founder handle, and a concrete why-flagged string."""
    gh = _strongest(signals, "github", "stars")
    if gh is not None:
        c = gh.content
        handle = (c.get("owner_profile") or {}).get("login") or c.get("repo", "").split("/")[0]
        return "github", handle, f"{c.get('stars', 0):,}★ ~{c.get('stars_per_day', 0)}/day ({c.get('repo')})"
    hn = _strongest(signals, "hn", "points")
    if hn is not None:
        c = hn.content
        return "hn", c.get("author", "?"), f"Show HN {c.get('points', 0)} pts ~{c.get('points_per_day', 0)}/day"
    handle = company.founders[0].github_handle or company.founders[0].name if company.founders else "?"
    return (signals[0].source if signals else "unknown"), handle, "sourced signal"


def _strongest(signals: list[Signal], source: str, metric: str) -> Signal | None:
    matches = [s for s in signals if s.source == source]
    if not matches:
        return None
    return max(matches, key=lambda s: s.content.get(metric, 0))


def _best_axis(scores: dict[str, float]) -> tuple[str | None, float | None]:
    if not scores:
        return None, None
    axis = max(scores, key=lambda k: scores[k])
    return axis, scores[axis]
