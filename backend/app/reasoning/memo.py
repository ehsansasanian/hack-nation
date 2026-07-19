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
from app.reasoning.mandate import MandateConstraint, evaluate_mandate_fit, render_mandate_fit
from app.reasoning.team import assess_team, founder_is_commercial, founder_is_technical
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
    thesis = _active_thesis(session)
    fit = thesis_fit(app.company, thesis)

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

    # Phase 8 deterministic sections, built backend-agnostically from stored data so
    # both backends produce them identically: Team & history (multi-founder only),
    # Bear case (from validator + truth-gap outputs), Mandate fit (constraints vs
    # realized values). Inserted after the five required sections.
    mandate_fit = evaluate_mandate_fit(
        thesis, ctx.company, ctx.founders, list(app.claims), ctx.scores,
        ctx.deck_text, ctx.evidence_signals,
    )
    team_section = _team_and_history_section(ctx)
    if team_section:
        rendered["Team & history"] = team_section
    rendered["Bear case"] = _bear_case_section(app, ctx, assessments, mandate_fit)
    fit_block = render_mandate_fit(mandate_fit)
    if fit_block:
        rendered["Mandate fit"] = fit_block

    recommendation = _recommendation(app, ctx, fit, assessments, mandate_fit)

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


def _team_and_history_section(ctx: DiligenceContext) -> str | None:
    """Per-founder background + complementarity verdict + gaps (multi-founder only)."""
    if len(ctx.founders) <= 1:
        return None
    sbf: dict[int, list] = {}
    for s in ctx.evidence_signals:
        if s.founder_id is not None:
            sbf.setdefault(s.founder_id, []).append(s)
    team = assess_team(ctx.founders, sbf, ctx.company.sector)

    lines: list[str] = []
    for f in ctx.founders:
        background = (f.bio or "background not disclosed").split(".")[0].strip()
        tech = founder_is_technical(f, sbf.get(f.id, []))
        comm = founder_is_commercial(f)
        role = (
            "technical + commercial" if tech and comm
            else "technical" if tech
            else "commercial" if comm
            else "role unclear"
        )
        score = f.founder_score if f.founder_score is not None else "unset"
        prior = [c.name for c in f.companies if c.id != ctx.company.id]
        returning = ""
        if prior or len(f.score_history or []) > 1:
            marker = ", ".join(prior) if prior else "score history on file"
            returning = f" Returning founder (prior: {marker})."
        lines.append(f"- {f.name} ({role}): {background}. Persistent founder_score {score}.{returning}")
    lines.append(f"- Complementarity: {team.verdict}.")
    if team.gaps:
        lines.append("- Flagged gaps: " + "; ".join(team.gaps) + ".")
    return "\n".join(lines)


def _bear_case_section(
    app: Application,
    ctx: DiligenceContext,
    assessments: list[ClaimAssessment],
    mandate_fit: list[MandateConstraint],
) -> str:
    """The explicit counter-argument, built ONLY from our stored validator + truth-gap
    outputs, weak axes, cold-start uncertainty and mandate gaps. Never claims an
    external market database we do not have."""
    lines: list[str] = []
    for s in ctx.scores:
        if s.validator_supported is False and s.validator_note:
            lines.append(
                f"- The self-correction validator could not fully support the "
                f"{s.axis.replace('_', ' ')} rationale: {s.validator_note}"
            )
    for a in assessments:
        if a.trust_level == "contradicted":
            note = a.contradiction_note or "a stored signal conflicts with this claim"
            lines.append(f"- Contradicted {a.category} claim: \"{a.text}\" - {note}")
    critical_unverified = [
        a for a in assessments
        if a.category in ("traction", "revenue") and a.trust_level == "unverified"
    ]
    for a in critical_unverified[:3]:
        lines.append(
            f"- Unverified {a.category} claim: \"{a.text}\" is taken at face value - "
            "no signal on file supports it."
        )
    for s in ctx.scores:
        if s.value <= 4.5:
            lines.append(
                f"- The {s.axis.replace('_', ' ')} axis is weak at {s.value}/10: "
                f"{(s.rationale or '').strip()}"
            )
    if ctx.cold_start:
        lines.append(
            "- Cold-start team: the founder read rests on potential, not an external "
            "track record - execution risk is real and the score carries wide uncertainty."
        )
    for c in mandate_fit:
        if c.status == "gap":
            lines.append(f"- Mandate gap: {c.label} - mandate wants {c.target}, realized {c.realized}.")

    if not lines:
        return (
            "No stored signal currently contradicts the thesis; the bear case rests on "
            "the absence of external validation rather than conflicting evidence. Treat "
            "the unverified claims as unproven until diligence closes them."
        )
    header = (
        "Arguing the other side, strictly from our own signals and scans (no external "
        "market database is claimed):"
    )
    return header + "\n" + "\n".join(lines)


def _recommendation(
    app: Application,
    ctx: DiligenceContext,
    fit: ThesisFit,
    assessments: list[ClaimAssessment],
    mandate_fit: list[MandateConstraint],
) -> str:
    scores = {s.axis: s.value for s in ctx.scores}
    f, m, i = scores.get("founder"), scores.get("market"), scores.get("idea_vs_market")
    core_contradicted = [
        a for a in assessments
        if a.category in ("traction", "revenue") and a.trust_level == "contradicted"
    ]
    has_strength = any(a.trust_level == "verified" for a in assessments) or (f is not None and f >= 7)
    # Hard mandate gaps that should temper a positive call (a configured constraint the
    # company clearly misses), kept separate from soft/unknown fit lines.
    hard_gaps = [
        c.label for c in mandate_fit
        if c.status == "gap" and c.label in ("Exclusions", "ARR floor", "Technical founder", "Growth floor")
    ]

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
    elif f is not None and f >= 7 and ((m or 0) >= 6.5 or (i or 0) >= 6.5) and not hard_gaps:
        verdict = "invest $100K"
        why = "clears the bar on the founder axis plus one more, in-thesis, no contradicted claims"
    elif f is not None and f >= 7 and ((m or 0) >= 6.5 or (i or 0) >= 6.5) and hard_gaps:
        verdict = "need-more-info"
        why = f"clears the axes but misses a hard mandate gate ({', '.join(hard_gaps)}) - resolve before committing"
    elif f is not None and m is not None and i is not None and min(f, m, i) >= 6:
        verdict = "need-more-info"
        why = "solid but not standout across all three axes"
    else:
        verdict = "pass"
        why = "does not clear the bar on the three axes"

    axes = f"founder {_fmt(f)}, market {_fmt(m)}, idea-vs-market {_fmt(i)}"
    scope = "in-thesis" if fit.in_scope else "out-of-thesis"
    tail = ""
    if mandate_fit:
        met = sum(c.status == "met" for c in mandate_fit)
        gap = sum(c.status == "gap" for c in mandate_fit)
        unknown = sum(c.status == "unknown" for c in mandate_fit)
        tail = f" Mandate fit: {met} met, {gap} gap, {unknown} unknown."
    return f"{verdict} - {why}. Axes (never averaged): {axes}. Thesis: {scope}.{tail}"


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
