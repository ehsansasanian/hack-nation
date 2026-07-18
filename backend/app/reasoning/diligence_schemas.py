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
    """The five required memo sections (Appendix 1). No padding beyond these."""

    company_snapshot: str
    investment_hypotheses: str
    swot: str
    problem_and_product: str
    traction_and_kpis: str


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
