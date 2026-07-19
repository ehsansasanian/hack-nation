"""Structured-output contracts shared by both diligence backends (Phase 4).

Mirrors ``reasoning/schemas.py``: one set of Pydantic models both the OpenAI
backend (via strict ``response_format``) and the deterministic offline backend
fill in, so the orchestrator never branches on which backend ran. Nullable fields
are represented as empty strings rather than ``None`` (strict structured-output
mode dislikes nullable), and the orchestrator normalises ``""`` -> ``None`` on the
way into the store.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ClaimCategory = Literal["traction", "revenue", "team", "market"]
TrustLevel = Literal["verified", "consistent", "unverified", "contradicted"]


class ExtractedClaim(BaseModel):
    """One discrete, checkable assertion pulled from a deck / self-asserted post."""

    text: str = Field(description="The claim as a single concise sentence.")
    category: ClaimCategory
    source: str = Field(description="Where it came from: deck / twitter / blog / hn.")


class ExtractedClaims(BaseModel):
    claims: list[ExtractedClaim]


class ClaimAssessment(BaseModel):
    """Truth-gap verdict for one claim, cross-referenced against stored signals."""

    text: str
    category: ClaimCategory
    source: str
    trust_level: TrustLevel = Field(
        description="verified (external evidence supports) / consistent (nothing "
        "contradicts) / unverified (no evidence either way) / contradicted (a "
        "signal conflicts)."
    )
    evidence_signal_ids: list[int] = Field(
        description="IDs of the signals that support or contradict this claim."
    )
    contradiction_note: str = Field(
        default="",
        description="When contradicted, name BOTH sources and the conflict; else empty.",
    )


class ClaimAssessments(BaseModel):
    assessments: list[ClaimAssessment]


class AxisCritique(BaseModel):
    """Validator's attempt to refute one axis rationale against the cited signals."""

    axis: str
    supported: bool = Field(description="False if the rationale is not backed by its evidence.")
    note: str = Field(description="What is (un)supported, referencing signal ids.")


class ClaimCritique(BaseModel):
    """Validator's re-check of one claim's assigned trust level."""

    index: int = Field(description="0-based index into the assessed-claim list.")
    revised_trust_level: TrustLevel = Field(description="Same level to keep, or a downgrade.")
    note: str = Field(default="", description="Reason for a change; empty if unchanged.")


class ValidatorReport(BaseModel):
    axis_critiques: list[AxisCritique]
    claim_critiques: list[ClaimCritique]


class MemoSections(BaseModel):
    """The memo's narrative sections.

    The first five are the required, evidence-backed sections (Appendix 1). The last
    four are the honestly-generatable analysis sections of the full VC checklist -
    real analysis, clearly labeled, never fabricated numbers: Technology &
    defensibility (proprietary-vs-commoditizable read from deck+signals), Market
    sizing (top-down/bottom-up WITH assumptions stated), Competition (named
    competitor clusters as analysis), Exit perspective (plausible paths, labeled
    hypothesis). Both backends fill all nine; padding is penalised - keep prose tight.
    """

    company_snapshot: str
    investment_hypotheses: str
    swot: str
    problem_and_product: str
    traction_and_kpis: str
    technology_defensibility: str = Field(
        default="",
        description="Proprietary-vs-commoditizable assessment from the deck + signals. "
        "Name what looks defensible vs forkable/commodity and the moat type, if any. "
        "An assessment, not a lab audit - no invented benchmarks.",
    )
    market_sizing: str = Field(
        default="",
        description="Top-down and/or bottom-up sizing with ASSUMPTIONS STATED EXPLICITLY. "
        "Any figure taken from the deck is marked as claimed/unverified; never invent a "
        "market number or an analyst source we do not hold.",
    )
    competition: str = Field(
        default="",
        description="Named competitor clusters as analysis (e.g. incumbents, "
        "open-source alternatives, big-tech platforms, point-solution startups) plus any "
        "competitors the deck names. Analysis, not a sourced database.",
    )
    exit_perspective: str = Field(
        default="",
        description="Plausible exit paths (strategic acquirers by archetype, IPO "
        "conditions), CLEARLY LABELED as a hypothesis. Directional only at pre-seed; "
        "does not affect the score.",
    )


class ParsedQuery(BaseModel):
    """A compound NL pipeline query parsed into structured filters."""

    sector: str = Field(default="", description="Thesis sector or empty if unspecified.")
    geography: str = Field(default="", description="City/region or empty if unspecified.")
    stage: str = Field(default="", description="Funding stage or empty if unspecified.")
    attributes: list[str] = Field(
        default_factory=list,
        description="Founder/company attributes, e.g. 'technical founder', "
        "'no prior vc backing', 'enterprise traction'.",
    )
