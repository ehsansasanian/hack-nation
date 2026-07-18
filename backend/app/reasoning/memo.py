"""Phase 4 memo generator.

``generate_memo`` produces the five required sections (Appendix 1) - Company
snapshot, Investment hypotheses, SWOT, Problem & product, Traction & KPIs - and
nothing else. The narrative prose comes from the diligence backend (LLM or
offline); the orchestrator then, backend-agnostically:

* renders every claim with its trust level (so it can never be silently dropped),
* flags missing data explicitly ("Cap table: not disclosed") - never fabricated,
* attaches a recommendation (invest $100K / pass / need-more-info) tied to thesis
  fit and the three axis scores, which are shown separately and never averaged.

The memo is upserted into the ``Memo`` table (a re-run replaces, never duplicates)
and the application is marked ``memo_ready``.
"""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, Claim, Memo
from app.reasoning.diligence import _active_thesis, _load_application, run_diligence
from app.reasoning.diligence_backend import get_diligence_backend
from app.reasoning.diligence_context import DiligenceContext, build_diligence_context
from app.reasoning.diligence_schemas import ClaimAssessment, MemoSections
from app.reasoning.thesis_fit import ThesisFit, thesis_fit

SECTION_TITLES = {
    "company_snapshot": "Company snapshot",
    "investment_hypotheses": "Investment hypotheses",
    "swot": "SWOT",
    "problem_and_product": "Problem & product",
    "traction_and_kpis": "Traction & KPIs",
}


@dataclass(slots=True)
class MemoOutcome:
    application_id: int
    backend: str
    recommendation: str
    sections: dict[str, str]
    fallback_from: str | None = None


def _claim_to_assessment(c: Claim) -> ClaimAssessment:
    return ClaimAssessment(
        text=c.text,
        category=c.category or "traction",
        source=c.source or "deck",
        trust_level=c.trust_level or "unverified",
        evidence_signal_ids=list(c.evidence_signal_ids or []),
        contradiction_note=c.contradiction_note or "",
    )


def generate_memo(
    session: Session,
    application_id: int,
    prefer_backend: str | None = None,
    allow_fallback: bool = True,
) -> MemoOutcome:
    app = _load_application(session, application_id)
    fit = thesis_fit(app.company, _active_thesis(session))

    # Diligence is the memo's input; run it if it has not been run yet.
    if not app.claims:
        run_diligence(session, application_id, prefer_backend=prefer_backend)
        app = _load_application(session, application_id)

    ctx = build_diligence_context(session, app, fit.rationale)
    assessments = [_claim_to_assessment(c) for c in app.claims]

    backend = get_diligence_backend(prefer_backend)
    fallback_from: str | None = None
    try:
        sections = backend.write_memo(ctx, assessments)
        backend_name = backend.name
    except OpenAIError as exc:
        if not (allow_fallback and backend.name != "offline-deterministic"):
            raise
        backend = get_diligence_backend("offline")
        sections = backend.write_memo(ctx, assessments)
        backend_name = backend.name
        fallback_from = f"openai ({type(exc).__name__})"

    rendered = _finalise_sections(sections, ctx, assessments)
    recommendation = _recommendation(app, ctx, fit, assessments)

    memo = _upsert_memo(session, application_id, rendered, recommendation)
    app.status = "memo_ready"
    session.commit()
    session.refresh(memo)
    return MemoOutcome(
        application_id=application_id,
        backend=backend_name,
        recommendation=recommendation,
        sections=memo.sections,
        fallback_from=fallback_from,
    )


def _finalise_sections(
    sections: MemoSections, ctx: DiligenceContext, assessments: list[ClaimAssessment]
) -> dict[str, str]:
    """Title-cased sections + backend-agnostic gap flags and claim-trust rendering."""
    raw = sections.model_dump()

    gaps = _missing_data_flags(ctx, assessments)
    if gaps:
        raw["company_snapshot"] += "\n\nNot disclosed: " + "; ".join(gaps) + "."

    if assessments:
        block = "\n".join(_render_claim(a) for a in assessments)
        raw["traction_and_kpis"] += "\n\nClaims & trust levels:\n" + block
    else:
        raw["traction_and_kpis"] += "\n\nNo checkable claims were stated in the application."

    return {SECTION_TITLES[key]: raw[key] for key in SECTION_TITLES}


def _render_claim(a: ClaimAssessment) -> str:
    line = f"- [{a.trust_level}] ({a.category}) {a.text}"
    if a.trust_level == "contradicted" and a.contradiction_note:
        line += f"\n    contradiction: {a.contradiction_note}"
    return line


# Topic -> the terms that, if present anywhere in the dossier, count as disclosure.
_GAP_TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cap table / ownership", ("cap table", "ownership", "equity", "% owned", "fully diluted")),
    ("Revenue / MRR", ("mrr", "arr", "revenue", "gross margin", "$ per")),
    ("Prior funding raised", ("raised", "seed round", "angel", "pre-seed round", "series")),
    ("Team size", ("team of", "headcount", "employees", "fte", "full-time")),
    ("Customer traction", ("customer", "users", "design partner", "pilot", "paying")),
)


def _missing_data_flags(ctx: DiligenceContext, assessments: list[ClaimAssessment]) -> list[str]:
    blob = " ".join(
        [ctx.deck_text, ctx.company.one_liner or ""]
        + [a.text for a in assessments]
        + [str(s.content) for s in ctx.evidence_signals]
    ).lower()
    return [label for label, terms in _GAP_TOPICS if not any(t in blob for t in terms)]


def _recommendation(
    app: Application, ctx: DiligenceContext, fit: ThesisFit, assessments: list[ClaimAssessment]
) -> str:
    scores = {s.axis: s.value for s in ctx.scores}
    f, m, i = scores.get("founder"), scores.get("market"), scores.get("idea_vs_market")
    core_contradicted = [
        a for a in assessments
        if a.category in ("traction", "revenue") and a.trust_level == "contradicted"
    ]
    has_strength = any(a.trust_level == "verified" for a in assessments) or (f is not None and f >= 7)

    if app.status == "screened_out" or not fit.in_scope:
        verdict = "pass"
        why = "out of thesis scope / screened out at first pass"
    elif len(core_contradicted) >= 2 and not has_strength:
        verdict = "pass"
        why = f"{len(core_contradicted)} core claims contradicted by diligence and no verified traction"
    elif core_contradicted:
        verdict = "need-more-info"
        why = "diligence caught overstated traction/revenue - verify the real numbers before a decision"
    elif ctx.cold_start:
        verdict = "need-more-info"
        why = "cold-start founder scored on potential - widen diligence before committing"
    elif f is not None and f >= 7 and ((m or 0) >= 6.5 or (i or 0) >= 6.5):
        verdict = "invest $100K"
        why = "clears the bar on the founder axis plus one more, in-thesis, no contradicted claims"
    elif f is not None and m is not None and i is not None and min(f, m, i) >= 6:
        verdict = "need-more-info"
        why = "solid but not standout across all three axes"
    else:
        verdict = "pass"
        why = "does not clear the bar on the three axes"

    axes = f"founder {_fmt(f)}, market {_fmt(m)}, idea-vs-market {_fmt(i)}"
    scope = "in-thesis" if fit.in_scope else "out-of-thesis"
    return f"{verdict} - {why}. Axes (never averaged): {axes}. Thesis: {scope}."


def _fmt(v: float | None) -> str:
    return f"{v}/10" if v is not None else "n/a"


def _upsert_memo(
    session: Session, application_id: int, sections: dict[str, str], recommendation: str
) -> Memo:
    memo = session.scalar(select(Memo).where(Memo.application_id == application_id))
    if memo is None:
        memo = Memo(application_id=application_id)
        session.add(memo)
    memo.sections = sections
    memo.recommendation = recommendation
    return memo
