"""Phase 6 agentic traceability: assemble the full reasoning chain per application.

Everything the chain needs is already persisted by Phases 1-4:

* signals, each source-tagged and timestamped (Phase 1),
* the screening verdict + rationale on the ``Application`` (Phase 2),
* per-axis ``Score`` rows carrying the cited evidence ids, rationale, cold-start
  range, confidence, model provenance, and validator note (Phase 2 + 4),
* per-claim ``Claim`` rows carrying the trust level, cited evidence ids,
  contradiction note, and validator note (Phase 4),
* the ``Memo`` with its recommendation (Phase 4).

``build_trace`` reads those rows and orders them into one coherent chain -

    signals ingested -> screening -> per-axis scoring -> claims + truth-gap -> memo

It never writes a new table and never duplicates data: every step points back at
the exact signal ids it reasoned over, and the resolved signal dossier is returned
alongside so a caller can render each cited signal's source, timestamp and excerpt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, selectinload

from app.models import Application, Company, Signal
from app.reasoning.context import build_context

# Canonical axis order and labels (kept local so this module stays import-light).
AXES = ("founder", "market", "idea_vs_market")
AXIS_LABELS = {"founder": "Founder", "market": "Market", "idea_vs_market": "Idea vs Market"}

# Trust level -> a plain-language truth-gap outcome for claims that carry no note.
_TRUST_SUMMARY = {
    "verified": "Supported by external evidence on file.",
    "consistent": "Nothing on file contradicts this claim.",
    "unverified": "No evidence either way - taken at face value, flagged in the memo.",
    "contradicted": "A stored signal conflicts with this claim.",
}


@dataclass(slots=True)
class TraceSignal:
    id: int
    source: str
    timestamp: object
    ingested_at: object
    excerpt: str
    content: dict


@dataclass(slots=True)
class TraceStep:
    index: int
    kind: str  # signals | screening | score | claim | memo
    title: str
    ref: str | None = None  # axis name (score) or claim id (claim)
    status: str | None = None  # verdict / trust level / recommendation verb
    summary: str = ""
    signal_ids: list[int] = field(default_factory=list)
    source_signal_id: int | None = None  # the signal the claim/step originated from
    detail: dict = field(default_factory=dict)


@dataclass(slots=True)
class Trace:
    application_id: int
    company: Company
    backend: str | None
    memo_recommendation: str | None
    signals: list[TraceSignal]
    steps: list[TraceStep]


def _excerpt(sig: Signal) -> str:
    """A short human-readable line for a signal's JSON content."""
    c = sig.content or {}
    for key in ("note", "text", "title", "summary", "headline"):
        if c.get(key):
            return str(c[key])
    if c.get("repo"):
        stars = c.get("stars")
        return f"{c['repo']}" + (f" - {stars} stars" if stars is not None else "")
    if c.get("kind") == "inbound_application":
        return "Inbound deck submission"
    if c.get("kind") == "pitch_deck":
        return str(c.get("excerpt") or c.get("file") or "Pitch deck")
    if c.get("excerpt"):
        return str(c["excerpt"])
    parts = [f"{k}: {v}" for k, v in c.items() if not isinstance(v, (dict, list))][:3]
    return " - ".join(parts) or sig.source


def _load_application(session: Session, application_id: int) -> Application:
    app = session.get(
        Application,
        application_id,
        options=[
            selectinload(Application.company).selectinload(Company.founders),
            selectinload(Application.scores),
            selectinload(Application.claims),
        ],
    )
    if app is None:
        raise LookupError(f"Application {application_id} not found.")
    return app


def build_trace(session: Session, application_id: int) -> Trace:
    app = _load_application(session, application_id)

    # The dossier: the union of every signal the scoring/diligence layers could have
    # cited (company signals + the persistent founder view), deduped and time-ordered.
    ctx = build_context(session, app, "")
    dossier = {s.id: s for s in (ctx.company_signals + ctx.founder_signals)}
    signals = sorted(dossier.values(), key=lambda s: s.timestamp)
    trace_signals = [
        TraceSignal(
            id=s.id,
            source=s.source,
            timestamp=s.timestamp,
            ingested_at=s.ingested_at,
            excerpt=_excerpt(s),
            content=dict(s.content or {}),
        )
        for s in signals
    ]
    # First signal seen per source, so a claim can point at the deck/post it came from.
    origin_by_source: dict[str, int] = {}
    for s in signals:
        origin_by_source.setdefault(s.source, s.id)

    memo = app.memo
    scores = {s.axis: s for s in app.scores}
    backend = next((s.model for s in app.scores if s.model), None)

    steps: list[TraceStep] = []

    # 1. Signals ingested.
    by_source = Counter(s.source for s in signals)
    source_blurb = ", ".join(f"{n} {src}" for src, n in sorted(by_source.items()))
    steps.append(
        TraceStep(
            index=len(steps),
            kind="signals",
            title="Signals ingested",
            summary=(
                f"{len(signals)} source-tagged, timestamped signals in the dossier"
                + (f" ({source_blurb})." if source_blurb else ".")
            ),
            signal_ids=[s.id for s in signals],
            detail={"by_source": dict(by_source)},
        )
    )

    # 2. Screening verdict.
    if app.screening_verdict:
        steps.append(
            TraceStep(
                index=len(steps),
                kind="screening",
                title="Screening verdict",
                status=app.screening_verdict,
                summary=app.screening_rationale or "",
            )
        )

    # 3. Per-axis scoring (independent axes, never averaged).
    for axis in AXES:
        score = scores.get(axis)
        if score is None:
            continue
        if score.cold_start and score.score_low is not None:
            display = f"{score.score_low}-{score.score_high}"
            value_note = f"cold-start range {display}/10 (midpoint {score.value})"
        else:
            display = str(score.value)
            value_note = f"{display}/10"
        steps.append(
            TraceStep(
                index=len(steps),
                kind="score",
                ref=axis,
                title=f"{AXIS_LABELS[axis]} axis",
                status=value_note,
                summary=score.rationale or "",
                signal_ids=list(score.evidence_signal_ids or []),
                detail={
                    "axis": axis,
                    "value": score.value,
                    "score_low": score.score_low,
                    "score_high": score.score_high,
                    "cold_start": score.cold_start,
                    "confidence": score.confidence,
                    "trend": score.trend,
                    "model": score.model,
                    "validator_note": score.validator_note,
                    # Where it lands: axis scores are cited verbatim in the memo recommendation.
                    "memo_section": "Recommendation" if memo else None,
                },
            )
        )

    # 4. Claims extracted + truth-gap outcome (one step per claim).
    core_contradicted = any(
        c.category in ("traction", "revenue") and c.trust_level == "contradicted"
        for c in app.claims
    )
    for claim in sorted(app.claims, key=lambda c: c.id):
        note = claim.contradiction_note or _TRUST_SUMMARY.get(claim.trust_level or "", "")
        influenced = (
            claim.trust_level == "contradicted"
            and claim.category in ("traction", "revenue")
        )
        steps.append(
            TraceStep(
                index=len(steps),
                kind="claim",
                ref=str(claim.id),
                title=claim.text,
                status=claim.trust_level,
                summary=note,
                signal_ids=list(claim.evidence_signal_ids or []),
                source_signal_id=origin_by_source.get(claim.source or "deck"),
                detail={
                    "claim_id": claim.id,
                    "category": claim.category,
                    "claim_source": claim.source,
                    "trust_level": claim.trust_level,
                    "contradiction_note": claim.contradiction_note,
                    "validator_note": claim.validator_note,
                    "memo_section": "Traction & KPIs" if memo else None,
                    "influenced_recommendation": influenced,
                },
            )
        )

    # 5. Memo generated.
    if memo:
        verb = (memo.recommendation or "").split(" - ")[0].strip() or None
        steps.append(
            TraceStep(
                index=len(steps),
                kind="memo",
                title="Investment memo",
                status=verb,
                summary=memo.recommendation or "",
                detail={
                    "sections": list(memo.sections.keys()) if memo.sections else [],
                    "core_contradiction": core_contradicted,
                },
            )
        )

    return Trace(
        application_id=app.id,
        company=app.company,
        backend=backend,
        memo_recommendation=memo.recommendation if memo else None,
        signals=trace_signals,
        steps=steps,
    )
