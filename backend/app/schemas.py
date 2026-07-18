"""Pydantic request/response models for the API contract."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompanyOut(_ORM):
    id: int
    name: str
    sector: str | None = None
    stage: str | None = None
    geography: str | None = None
    one_liner: str | None = None


class FounderOut(_ORM):
    id: int
    name: str
    github_handle: str | None = None
    links: dict = {}
    bio: str | None = None
    founder_score: float | None = None
    score_history: list = []


class SignalOut(_ORM):
    id: int
    source: str
    content: dict = {}
    timestamp: datetime
    ingested_at: datetime
    last_seen: datetime


class ScoreOut(_ORM):
    axis: str
    value: float
    trend: str | None = None
    rationale: str | None = None
    evidence_signal_ids: list = []
    confidence: float | None = None
    cold_start: bool = False
    score_low: float | None = None
    score_high: float | None = None
    model: str | None = None


class ClaimOut(_ORM):
    text: str
    category: str | None = None
    trust_level: str | None = None
    evidence_signal_ids: list = []
    contradiction_note: str | None = None


class ApplicationOut(_ORM):
    """Pipeline row: application header + company + any scores computed so far."""

    id: int
    status: str
    origin: str
    screening_verdict: str | None = None
    screening_rationale: str | None = None
    created_at: datetime
    company: CompanyOut
    scores: list[ScoreOut] = []


class ApplicationDetailOut(ApplicationOut):
    deck_text: str | None = None
    claims: list[ClaimOut] = []
    founders: list[FounderOut] = []


class FounderDetailOut(FounderOut):
    companies: list[CompanyOut] = []
    signals: list[SignalOut] = []


class ApplicationCreate(BaseModel):
    """Inbound application: a company name plus optional deck text and metadata."""

    company_name: str
    deck_text: str | None = None
    founder_name: str | None = None
    sector: str | None = None
    stage: str | None = None
    geography: str | None = None
    one_liner: str | None = None


class ThesisOut(_ORM):
    id: int
    name: str
    sectors: list = []
    stages: list = []
    geographies: list = []
    check_size: str | None = None
    ownership_target: str | None = None
    risk_appetite: str | None = None
    active: bool = True


class ThesisUpdate(BaseModel):
    name: str
    sectors: list[str] = []
    stages: list[str] = []
    geographies: list[str] = []
    check_size: str | None = None
    ownership_target: str | None = None
    risk_appetite: str | None = None
    active: bool = True


class ThesisFitOut(BaseModel):
    in_scope: bool
    out_of_scope_reasons: list[str] = []
    rationale: str


class ScoringResultOut(_ORM):
    """Result of running the Phase 2 reasoning pipeline on one application."""

    application_id: int
    status: str
    backend: str  # which reasoning backend produced the scores
    thesis_fit: ThesisFitOut
    screening_verdict: str | None = None
    screening_rationale: str | None = None
    cold_start: bool = False
    scores: list[ScoreOut] = []
