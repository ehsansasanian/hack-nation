"""Phase 4 diligence orchestrator: claim extraction -> truth-gap -> validator.

``run_diligence`` is the single entry point the API and CLI call. It mirrors
``reasoning.service.score_application``:

1. Build the diligence context (deck + self-asserted claim sources + evidence).
2. Extract claims (backend).
3. Truth-gap each claim against the evidence signals (backend), validating every
   cited signal_id against the evidence universe (hallucinated ids dropped).
4. Validator self-correction pass: refute axis rationales, downgrade
   over-optimistic claim trust levels. Outcomes are stored (Claim.validator_note,
   Score.validator_note) so the signal -> claim -> trust -> memo chain stays
   auditable for Phase 6 traceability.

A live-call failure falls back to the deterministic offline backend, and the
fallback is recorded on the outcome - identical to the scoring seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Claim, Company, Score, Thesis
from app.reasoning.context import ensure_team_resolved
from app.reasoning.diligence_backend import DiligenceBackend, get_diligence_backend
from app.reasoning.diligence_context import DiligenceContext, build_diligence_context
from app.reasoning.diligence_schemas import ClaimAssessment
from app.reasoning.thesis_fit import thesis_fit


@dataclass(slots=True)
class DiligenceOutcome:
    application_id: int
    backend: str
    claims: list[Claim] = field(default_factory=list)
    unsupported_axes: list[str] = field(default_factory=list)
    fallback_from: str | None = None

    @property
    def n_contradicted(self) -> int:
        return sum(c.trust_level == "contradicted" for c in self.claims)

    @property
    def n_verified(self) -> int:
        return sum(c.trust_level == "verified" for c in self.claims)


def _active_thesis(session: Session) -> Thesis | None:
    return session.scalar(select(Thesis).order_by(Thesis.id.desc()))


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


def _validate_ids(ids: list[int], universe: set[int]) -> list[int]:
    """Keep only cited ids that were actually in the evidence universe."""
    return [i for i in dict.fromkeys(ids) if i in universe]


def run_diligence(
    session: Session,
    application_id: int,
    prefer_backend: str | None = None,
    allow_fallback: bool = True,
) -> DiligenceOutcome:
    app = _load_application(session, application_id)
    # Make sure every declared co-founder is attached (idempotent) so team claims can
    # cross-reference each founder's enrichment signals even on a diligence-only run.
    ensure_team_resolved(session, app)
    fit = thesis_fit(app.company, _active_thesis(session))
    ctx = build_diligence_context(session, app, fit.rationale)

    backend = get_diligence_backend(prefer_backend)
    try:
        return _run(session, app, ctx, backend)
    except OpenAIError as exc:
        if not (allow_fallback and backend.name != "offline-deterministic"):
            raise
        session.rollback()
        app = _load_application(session, application_id)
        ctx = build_diligence_context(session, app, fit.rationale)
        outcome = _run(session, app, ctx, get_diligence_backend("offline"))
        outcome.fallback_from = f"openai ({type(exc).__name__})"
        return outcome


def _run(
    session: Session, app: Application, ctx: DiligenceContext, backend: DiligenceBackend
) -> DiligenceOutcome:
    universe = ctx.evidence_ids()

    # 1 + 2. Extract, then truth-gap each claim.
    extracted = backend.extract_claims(ctx)
    assessments = backend.assess_claims(ctx, extracted)
    for a in assessments:
        a.evidence_signal_ids = _validate_ids(a.evidence_signal_ids, universe)

    # 3. Validator self-correction.
    report = backend.validate(ctx, assessments)
    claim_notes = _apply_claim_critiques(assessments, report)
    unsupported = _apply_axis_critiques(ctx.scores, report)

    # 3b. Evidence gate (backend-agnostic): a 'contradicted' verdict must trace to
    #     real conflicting evidence. Anything marked contradicted without a
    #     substantive note or a valid conflicting signal is downgraded to unverified.
    _enforce_contradictions(assessments, claim_notes, universe)

    # 4. Persist - clean upsert so re-running never duplicates claims.
    _replace_claims(session, app.id, assessments, claim_notes, universe)
    session.commit()

    # Fresh read (session keeps objects unexpired after commit, so re-query).
    claims = list(
        session.scalars(
            select(Claim).where(Claim.application_id == app.id).order_by(Claim.id)
        )
    )
    return DiligenceOutcome(
        application_id=app.id,
        backend=backend.name,
        claims=claims,
        unsupported_axes=unsupported,
    )


def _apply_claim_critiques(
    assessments: list[ClaimAssessment], report
) -> dict[int, str | None]:
    """Apply validator downgrades in place; return per-claim validator notes."""
    notes: dict[int, str | None] = {}
    for critique in report.claim_critiques:
        i = critique.index
        if not 0 <= i < len(assessments):
            continue
        if critique.revised_trust_level != assessments[i].trust_level:
            assessments[i].trust_level = critique.revised_trust_level
            notes[i] = critique.note or "trust level revised by validator"
        elif critique.note:
            notes[i] = critique.note
    return notes


def _is_substantive_note(note: str | None) -> bool:
    """A contradiction note must carry real content, not be blank or a stub."""
    return bool(note) and len(note.strip()) >= 12


def _enforce_contradictions(
    assessments: list[ClaimAssessment],
    notes: dict[int, str | None],
    universe: set[int],
) -> None:
    """Hard gate for the ``contradicted`` trust level, applied to every backend.

    A contradiction must trace to actual conflicting evidence: a valid conflicting
    ``evidence_signal_id`` AND a substantive ``contradiction_note`` naming the
    conflict. A claim marked ``contradicted`` without both is a model asserting a
    conflict it cannot back up - it is downgraded to ``unverified`` (absence of
    evidence is not a contradiction). The downgrade is never silent: its reason is
    recorded on ``validator_note`` so the signal -> claim -> trust chain stays
    auditable for traceability.
    """
    for i, a in enumerate(assessments):
        if a.trust_level != "contradicted":
            continue
        has_signal = bool(_validate_ids(a.evidence_signal_ids, universe))
        has_note = _is_substantive_note(a.contradiction_note)
        if has_signal and has_note:
            continue  # a real, evidenced contradiction - keep it.
        if not has_signal and not has_note:
            missing = "cites no conflicting evidence signal and gives no contradiction note"
        elif not has_signal:
            missing = "cites no conflicting evidence signal"
        else:
            missing = "gives no substantive contradiction note"
        reason = (
            f"Downgraded contradicted->unverified: {missing}; a contradiction must "
            "trace to a real conflicting signal."
        )
        a.trust_level = "unverified"
        a.contradiction_note = ""
        existing = notes.get(i)
        notes[i] = f"{existing} {reason}".strip() if existing else reason


def _apply_axis_critiques(scores: list[Score], report) -> list[str]:
    """Stamp validator notes + supported flag on the axis scores; return unsupported."""
    by_axis = {s.axis: s for s in scores}
    unsupported: list[str] = []
    for critique in report.axis_critiques:
        score = by_axis.get(critique.axis)
        if score is None:
            continue
        score.validator_note = critique.note
        score.validator_supported = bool(critique.supported)
        if not critique.supported:
            unsupported.append(critique.axis)
    return unsupported


def _replace_claims(
    session: Session,
    application_id: int,
    assessments: list[ClaimAssessment],
    notes: dict[int, str | None],
    universe: set[int],
) -> None:
    session.query(Claim).filter(Claim.application_id == application_id).delete()
    for i, a in enumerate(assessments):
        session.add(
            Claim(
                application_id=application_id,
                text=a.text,
                category=a.category,
                source=a.source,
                trust_level=a.trust_level,
                evidence_signal_ids=_validate_ids(a.evidence_signal_ids, universe),
                contradiction_note=a.contradiction_note or None,
                validator_note=notes.get(i),
            )
        )
