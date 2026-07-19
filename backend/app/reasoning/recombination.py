"""Co-founder & idea recombination (Phase 8) - the innovation-criterion play.

For a *low-scoring* application, the brain asks a different question than "invest or
pass": **what would have to change for this to become investible?** It

1. reads the weak axis / gaps from the stored scores + the deterministic team read
   (never re-scores, never mutates a Score),
2. searches Memory for complementary founders - skill/domain complementarity, and
   ``availability`` defined as *not tied to an active in-thesis application* (a
   founder we are already funding/pursuing is off the market; a founder whose only
   ventures exited, wound down, were screened out or fall out of thesis is
   recombinable talent),
3. suggests idea pivots, and
4. emits a CONTINGENT IC note ("investible if X joins / pivot validated -
   re-evaluate in N weeks") that is ALWAYS explicitly labeled hypothetical.

Dual backend, kept consistent: the candidate shortlist, gaps and pivots are fully
deterministic on both paths (so the two never disagree on *who* is proposed); only
the closing narrative differs - an LLM writes it on the openai path (cheap
gpt-4o-mini), a deterministic template writes it offline. The result is upserted
into the ``RecombinationNote`` table (its own table - hypothetical, never the memo).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

from openai import OpenAI, OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import OPENAI_API_KEY
from app.models import Application, Company, Founder, RecombinationNote, Score, Thesis
from app.reasoning.context import build_context
from app.reasoning.team import assess_team, founder_is_commercial, founder_is_technical
from app.reasoning.thesis_fit import thesis_fit

# An axis at or below this is "weak" enough to motivate recombination.
WEAK_AXIS_THRESHOLD = 5.5
# Sectors that read as technically adjacent (partial domain credit).
_ADJACENT = ({"ai infra", "devtools"}, {"fintech"}, {"health"})
_HYPE = ("blockchain", "metaverse", "synergy", "web3", "crypto", "nft", "revolutioniz", "frictionless")

NARRATIVE_MODEL = "gpt-4o-mini"  # the contingent note is cheap prose, not scoring


@dataclass(slots=True)
class Candidate:
    founder_id: int
    name: str
    sector: str | None
    founder_score: float | None
    technical: bool
    commercial: bool
    fills: list[str]  # which team gap(s) they close: technical / commercial / domain
    availability: str  # human-readable "why they are recombinable"
    why: str  # one-line complementarity rationale
    match_score: float


@dataclass(slots=True)
class RecombinationResult:
    application_id: int
    company: str
    standing: str  # the current, real standing (unchanged by this note)
    weak_axes: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    idea_pivots: list[str] = field(default_factory=list)
    contingent_note: str = ""
    reeval_weeks: int = 8
    backend: str = "offline-deterministic"


# --- availability ------------------------------------------------------------


def _availability(founder: Founder, thesis: Thesis | None) -> tuple[bool, str]:
    """Available = the founder is not tied to an *active in-thesis* application.

    Active in-thesis = an application that is in thesis scope and not screened out
    (i.e. a live deal we are pursuing). Returns (available, human label).
    """
    for c in founder.companies:
        for app in c.applications:
            if app.status != "screened_out" and thesis_fit(c, thesis).in_scope:
                return False, f"committed to active in-thesis venture {c.name}"
    # Available - describe the honest reason so the suggestion is auditable.
    notes: list[str] = []
    for c in founder.companies:
        stage = (c.stage or "").lower()
        if stage == "acquired":
            notes.append(f"{c.name} exited (acquired)")
        elif stage in ("shut_down", "shutdown", "wound_down"):
            notes.append(f"{c.name} wound down")
    if notes:
        return True, "; ".join(notes) + " - between ventures"
    return True, "no live in-thesis deal in the pipeline - recombinable"


# --- gap / need detection ----------------------------------------------------


def _team_needs(technical: bool, commercial: bool, domain_gap: bool, solo: bool) -> set[str]:
    needs: set[str] = set()
    if not technical or domain_gap:
        needs.add("technical")
    if not commercial:
        needs.add("commercial")
    return needs


def _sector_domain_credit(cand_sectors: set[str], target: str | None) -> float:
    t = (target or "").strip().lower()
    if not t:
        return 0.0
    if t in cand_sectors:
        return 1.5
    for group in _ADJACENT:
        if t in group and cand_sectors & group:
            return 0.75
    return 0.0


def _founder_sectors(founder: Founder) -> set[str]:
    return {(c.sector or "").strip().lower() for c in founder.companies if c.sector}


def _has_exit(founder: Founder) -> bool:
    return any((c.stage or "").lower() == "acquired" for c in founder.companies)


# --- candidate ranking -------------------------------------------------------


def _rank_candidates(
    session: Session,
    target_founder_ids: set[int],
    target_sector: str | None,
    needs: set[str],
    thesis: Thesis | None,
) -> list[Candidate]:
    pool = session.scalars(
        select(Founder).options(
            selectinload(Founder.companies).selectinload(Company.applications),
            selectinload(Founder.signals),
        )
    ).all()

    ranked: list[Candidate] = []
    for f in pool:
        if f.id in target_founder_ids:
            continue  # cannot recombine a team with its own member
        available, avail_label = _availability(f, thesis)
        if not available:
            continue

        tech = founder_is_technical(f, list(f.signals))
        comm = founder_is_commercial(f)
        sectors = _founder_sectors(f)
        fs = f.founder_score or 0.0

        fills: list[str] = []
        score = 0.0
        # Filling the actual named gap dominates - that is the point of the proposal.
        if "technical" in needs and tech:
            score += 4.0
            fills.append("technical")
        if "commercial" in needs and comm:
            score += 4.0
            fills.append("commercial")
        domain = _sector_domain_credit(sectors, target_sector)
        if domain >= 1.5:
            fills.append("domain")
        score += domain
        score += min(2.0, fs / 5.0)  # strength anchor (persistent founder score)
        score += 1.0 if _has_exit(f) else (0.75 if len(f.companies) > 1 else 0.0)
        if f.github_handle:
            score += 0.5

        # Only propose a founder who adds something concrete: fills a named gap, or
        # is a strong/proven operator worth pairing. Skip thin, empty profiles.
        if not fills and fs < 6.0:
            continue

        role = (
            "technical + commercial" if tech and comm
            else "technical" if tech else "commercial" if comm else "operator"
        )
        sector_str = ", ".join(sorted(s for s in sectors if s)) or "unlisted sector"
        strength = f"founder score {fs:.1f}" if fs else "no prior VC score on file"
        exit_note = " (prior exit)" if _has_exit(f) else ""
        covers = (
            f"Covers the team's {', '.join(fills)} gap."
            if fills
            else "Adds a proven execution track record."
        )
        why = f"{f.name} - {role} founder from {sector_str}{exit_note}; {strength}. {covers}"
        ranked.append(
            Candidate(
                founder_id=f.id,
                name=f.name,
                sector=", ".join(sorted(sectors)) or None,
                founder_score=f.founder_score,
                technical=tech,
                commercial=comm,
                fills=fills,
                availability=avail_label,
                why=why,
                match_score=round(score, 2),
            )
        )

    ranked.sort(key=lambda c: (c.match_score, c.founder_score or 0), reverse=True)
    return ranked[:3]


# --- idea pivots -------------------------------------------------------------


def _idea_pivots(company: Company, blob: str, contradicted: bool) -> list[str]:
    sector = company.sector or "the target"
    low = blob.lower()
    pivots: list[str] = []
    if any(t in low for t in _HYPE):
        pivots.append(
            f"Drop the buzzword framing and commit to one concrete {sector} workflow; "
            "validate it with ~5 design partners before re-pitching."
        )
    if "crowded" in low or "undifferentiated" in low:
        pivots.append(
            f"Differentiate on a narrow wedge rather than the broad {sector} category - "
            "own one repeatable use case first."
        )
    if contradicted:
        pivots.append(
            "Re-baseline the overstated traction/funding claims to independently "
            "verifiable numbers before the next raise."
        )
    if not pivots:
        pivots.append(
            f"Sharpen the ICP to a single {sector} buyer and prove one repeatable use "
            "case, then re-evaluate."
        )
    return pivots[:3]


# --- standing + note ---------------------------------------------------------


def _standing(app: Application, scores: list[Score], weak_axes: list[dict], cold_start: bool) -> str:
    if app.status == "screened_out":
        reason = app.screening_rationale or "no substantiating signal at first pass"
        return f"screened out at first pass ({reason.rstrip('.').lower()})"
    if weak_axes:
        w = weak_axes[0]
        tail = "; team scored cold-start on potential" if cold_start else ""
        return f"below the bar, weakest on the {w['axis'].replace('_', ' ')} axis at {w['value']}/10{tail}"
    if cold_start:
        return "a cold-start hold - scored on potential with wide uncertainty"
    return "a hold pending stronger evidence"


def _reeval_weeks(app: Application, cold_start: bool) -> int:
    weeks = 8
    if app.status == "screened_out" or cold_start:
        weeks += 4
    return min(weeks, 12)


def _condition_clause(candidates: list[Candidate], pivots: list[str]) -> str:
    clauses: list[str] = []
    if candidates:
        top = candidates[0]
        fill = top.fills[0] if top.fills else "complementary"
        clauses.append(f"a {fill} co-founder such as {top.name} joins the team")
    if pivots:
        clauses.append(f"the idea is validated along a sharper wedge ({pivots[0].rstrip('.')})")
    return " and/or ".join(clauses) or "the gaps below are closed"


def _deterministic_note(
    company: str, standing: str, candidates: list[Candidate], pivots: list[str], weeks: int
) -> str:
    condition = _condition_clause(candidates, pivots)
    return (
        f"HYPOTHETICAL - NOT A REAL IC RECOMMENDATION. As assessed, {company} is {standing}. "
        f"It could become investible IF {condition}. Re-evaluate in {weeks} weeks once the "
        "condition is demonstrated. The three axis scores above are unchanged - this note "
        "explores a what-if and never overwrites the real assessment."
    )


def _openai_note(
    company: str, standing: str, gaps: list[str], candidates: list[Candidate],
    pivots: list[str], weeks: int,
) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    cand_lines = "\n".join(f"- {c.why} (availability: {c.availability})" for c in candidates) or "(none found)"
    pivot_lines = "\n".join(f"- {p}" for p in pivots)
    user = (
        f"COMPANY: {company}\n"
        f"CURRENT REAL STANDING (do not change this): {standing}\n"
        f"TEAM GAPS: {', '.join(gaps) or 'none named'}\n"
        f"COMPLEMENTARY FOUNDERS FROM OUR MEMORY (already shortlisted, do not invent others):\n{cand_lines}\n"
        f"IDEA PIVOTS:\n{pivot_lines}\n"
        f"RE-EVALUATE WINDOW: {weeks} weeks\n\n"
        "Write a CONTINGENT IC note of 3-5 sentences. Requirements: (1) open by stating it "
        "is HYPOTHETICAL and not a real recommendation; (2) name the IF-condition - a "
        "complementary co-founder joining and/or the pivot being validated; (3) state the "
        f"re-evaluate-in-{weeks}-weeks window; (4) end by making clear the real axis scores "
        "are unchanged. Use only the founders and facts given - never invent traction, "
        "funding, or people."
    )
    completion = client.chat.completions.create(
        model=NARRATIVE_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a disciplined pre-seed VC analyst writing an explicitly "
                    "hypothetical, contingent note. You never invent facts and never present "
                    "a what-if as a real decision."
                ),
            },
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    # Fold token usage into the shared accumulator so run-cost reporting stays honest.
    if completion.usage is not None:
        from app.reasoning.openai_backend import USAGE

        USAGE.add(NARRATIVE_MODEL, completion.usage.prompt_tokens, completion.usage.completion_tokens)
    return (completion.choices[0].message.content or "").strip()


# --- orchestrator ------------------------------------------------------------


def _use_llm(prefer_backend: str | None) -> bool:
    mode = (prefer_backend or os.getenv("VC_BRAIN_LLM", "auto")).strip().lower()
    if mode == "offline":
        return False
    return mode == "openai" or (mode == "auto" and bool(OPENAI_API_KEY))


def generate_recombination(
    session: Session, application_id: int, prefer_backend: str | None = None
) -> RecombinationResult:
    """Build (and persist) the recombination note for one application.

    Read-only with respect to the assessment: it reads scores + the team read and
    writes ONLY the ``RecombinationNote`` row. Real Score rows are never touched.
    """
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

    thesis = session.scalar(select(Thesis).order_by(Thesis.id.desc()))
    ctx = build_context(session, app, thesis_rationale="", thesis=thesis)  # read-only

    scores = list(app.scores)
    weak_axes = [
        {"axis": s.axis, "value": s.value, "note": (s.rationale or "").split(".")[0][:160]}
        for s in sorted(scores, key=lambda s: s.value)
        if s.value <= WEAK_AXIS_THRESHOLD or s.cold_start
    ]

    signals_by_founder = {f.id: ctx.signals_for(f.id) for f in ctx.founders}
    team = assess_team(ctx.founders, signals_by_founder, ctx.company.sector)
    needs = _team_needs(team.technical, team.commercial, team.domain_gap, team.solo)

    gaps: list[str] = list(team.gaps)
    contradicted = any(
        c.trust_level == "contradicted" and c.category in ("traction", "revenue")
        for c in app.claims
    )
    if contradicted:
        gaps.append("overstated traction/funding claims contradicted by diligence")

    target_founder_ids = {f.id for f in ctx.founders}
    candidates = _rank_candidates(session, target_founder_ids, ctx.company.sector, needs, thesis)

    blob = " ".join([app.deck_text or "", app.company.one_liner or ""] + [c.text for c in app.claims])
    pivots = _idea_pivots(app.company, blob, contradicted)

    standing = _standing(app, scores, weak_axes, ctx.cold_start)
    weeks = _reeval_weeks(app, ctx.cold_start)

    backend = "offline-deterministic"
    note = _deterministic_note(app.company.name, standing, candidates, pivots, weeks)
    if _use_llm(prefer_backend):
        try:
            note = _openai_note(app.company.name, standing, gaps, candidates, pivots, weeks)
            backend = NARRATIVE_MODEL
        except OpenAIError:
            backend = "offline-deterministic (openai fallback)"

    result = RecombinationResult(
        application_id=application_id,
        company=app.company.name,
        standing=standing,
        weak_axes=weak_axes,
        gaps=gaps,
        candidates=candidates,
        idea_pivots=pivots,
        contingent_note=note,
        reeval_weeks=weeks,
        backend=backend,
    )
    _upsert_note(session, result)
    return result


def _upsert_note(session: Session, result: RecombinationResult) -> RecombinationNote:
    note = session.scalar(
        select(RecombinationNote).where(RecombinationNote.application_id == result.application_id)
    )
    if note is None:
        note = RecombinationNote(application_id=result.application_id)
        session.add(note)
    note.standing = result.standing
    note.weak_axes = result.weak_axes
    note.gaps = result.gaps
    note.candidates = [asdict(c) for c in result.candidates]
    note.idea_pivots = result.idea_pivots
    note.contingent_note = result.contingent_note
    note.reeval_weeks = result.reeval_weeks
    note.backend = result.backend
    session.commit()
    session.refresh(note)
    return note
