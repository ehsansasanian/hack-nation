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
    validator_note: str | None = None


class ClaimOut(_ORM):
    id: int
    text: str
    category: str | None = None
    source: str | None = None
    trust_level: str | None = None
    evidence_signal_ids: list = []
    contradiction_note: str | None = None
    validator_note: str | None = None


class ApplicationOut(_ORM):
    """Pipeline row: application header + company + any scores computed so far."""

    id: int
    status: str
    # Auto-analysis stage: received|screening|scoring|diligence|memo|ready|screened_out|failed
    analysis_status: str = "received"
    analysis_error: str | None = None
    origin: str
    screening_verdict: str | None = None
    screening_rationale: str | None = None
    outreach_draft: str | None = None  # set only on activated outbound candidates
    # Inbound enrichment: per-source fetch report set by the ``enriching`` stage,
    # e.g. {"github": {"outcome": "fetched", "signal_count": 12},
    #       "linkedin": {"outcome": "blocked", "signal_count": 1, "note": "..."}}.
    enrichment_report: dict | None = None
    created_at: datetime
    company: CompanyOut
    scores: list[ScoreOut] = []


class ApplicationDetailOut(ApplicationOut):
    deck_text: str | None = None
    claims: list[ClaimOut] = []
    founders: list[FounderOut] = []
    declared_links: list | None = None  # self-declared per-founder links from apply


class FounderDetailOut(FounderOut):
    companies: list[CompanyOut] = []
    signals: list[SignalOut] = []


class AnalyzeOut(BaseModel):
    """Result of scheduling (or declining to schedule) an auto-analysis run."""

    application_id: int
    analysis_status: str
    scheduled: bool  # False = a run was already in flight, or already analysed (no force)
    detail: str


class FounderLinksIn(BaseModel):
    """Optional self-declared links for one founder, collected on apply.

    Everything is optional - over-collecting works against us and a missing link
    must never penalise a founder (cold-start protection stays). Handles may be
    given bare (``octocat``) or as full URLs; the enrichment stage normalises them.
    """

    name: str | None = None
    github: str | None = None  # handle or profile URL
    linkedin: str | None = None  # profile URL (typically auth-walled)
    website: str | None = None  # personal site / blog URL
    x: str | None = None  # handle or profile URL (X / Twitter, typically auth-walled)
    other_links: list[str] = []


class ApplicationCreate(BaseModel):
    """Inbound application: a company name plus optional deck text and metadata.

    ``founders`` carries optional per-founder self-declared links (github / linkedin
    / website / x) that the ``enriching`` stage fetches before screening. The legacy
    flat ``founder_name`` stays for backward compatibility; when ``founders`` is set
    it takes precedence and the first entry is treated as the primary founder.
    """

    company_name: str
    deck_text: str | None = None
    founder_name: str | None = None
    sector: str | None = None
    stage: str | None = None
    geography: str | None = None
    one_liner: str | None = None
    founders: list[FounderLinksIn] = []


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
    # --- Phase 8: customizable fund guidelines + investor-vocabulary constraints ---
    investment_principles: str | None = None
    axis_notes: dict | None = None  # {founder/market/idea_vs_market: emphasis note}
    valuation_cap: str | None = None
    instrument: str | None = None
    business_model: str | None = None
    min_arr_usd: float | None = None
    min_growth_rate: str | None = None
    require_technical_founder: bool | None = None
    exclusions: list | None = None


class ThesisUpdate(BaseModel):
    name: str
    sectors: list[str] = []
    stages: list[str] = []
    geographies: list[str] = []
    check_size: str | None = None
    ownership_target: str | None = None
    risk_appetite: str | None = None
    active: bool = True
    # --- Phase 8 (all optional; omitting a field clears/keeps it as sent) ---
    investment_principles: str | None = None
    axis_notes: dict[str, str] = {}
    valuation_cap: str | None = None
    instrument: str | None = None
    business_model: str | None = None
    min_arr_usd: float | None = None
    min_growth_rate: str | None = None
    require_technical_founder: bool = False
    exclusions: list[str] = []


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


# --- Phase 4: diligence, trust score & memo ---------------------------------


class DiligenceResultOut(BaseModel):
    """Result of running the Phase 4 diligence pipeline on one application."""

    application_id: int
    backend: str  # which diligence backend produced the claims
    n_claims: int
    n_contradicted: int
    n_verified: int
    unsupported_axes: list[str] = []  # axes the validator could not support
    claims: list[ClaimOut] = []


class MemoOut(_ORM):
    """Investment memo: the five required sections + a scores-tied recommendation."""

    application_id: int
    sections: dict = {}  # {section title: markdown/prose}
    recommendation: str | None = None
    generated_at: datetime


# --- Phase 6: agentic traceability ------------------------------------------


class TraceSignalOut(_ORM):
    """A signal in the application dossier, resolved for the trace panel."""

    id: int
    source: str
    timestamp: datetime
    ingested_at: datetime
    excerpt: str
    content: dict = {}


class TraceStepOut(_ORM):
    """One ordered step in the reasoning chain."""

    index: int
    kind: str  # signals | screening | score | claim | memo
    title: str
    ref: str | None = None  # axis name (score) or claim id (claim), for UI anchoring
    status: str | None = None  # verdict / score / trust level / recommendation verb
    summary: str = ""
    signal_ids: list[int] = []  # signals this step reasoned over
    source_signal_id: int | None = None  # the signal a claim was extracted from
    detail: dict = {}


class TraceOut(_ORM):
    """The full, ordered reasoning chain for one application, assembled from
    existing rows (no separate trace log): signals -> screening -> per-axis
    scoring -> claims + truth-gap -> memo, with the resolved signal dossier."""

    application_id: int
    company: CompanyOut
    backend: str | None = None  # model provenance stamped on the scores
    memo_recommendation: str | None = None
    signals: list[TraceSignalOut] = []
    steps: list[TraceStepOut] = []


# --- Phase 8: co-founder & idea recombination -------------------------------


class RecombinationCandidateOut(BaseModel):
    """One complementary founder proposed from Memory (hypothetical)."""

    founder_id: int
    name: str
    sector: str | None = None
    founder_score: float | None = None
    technical: bool = False
    commercial: bool = False
    fills: list[str] = []  # gaps this founder would close: technical / commercial / domain
    availability: str = ""  # why they are recombinable (not tied to an active in-thesis deal)
    why: str = ""  # complementarity rationale
    match_score: float = 0.0


class RecombinationOut(BaseModel):
    """A HYPOTHETICAL recombination note for a low-scoring application.

    Complementary co-founder proposals + idea pivots + a contingent IC note. Never
    reflects a change to the real axis scores - it is a what-if, clearly labeled.
    """

    application_id: int
    company: str
    standing: str  # the current, real standing (unchanged by this note)
    weak_axes: list[dict] = []
    gaps: list[str] = []
    candidates: list[RecombinationCandidateOut] = []
    idea_pivots: list[str] = []
    contingent_note: str = ""
    reeval_weeks: int = 8
    backend: str = "offline-deterministic"


# --- Phase 3: outbound sourcing ---------------------------------------------


class ScanRequest(BaseModel):
    """Trigger an outbound scan. Defaults are modest to stay fast and rate-safe."""

    sources: list[str] = ["github", "hn"]
    limit: int = 10  # candidates per source


class ScanCandidateOut(_ORM):
    source: str
    handle: str
    company: str
    why_flagged: str
    status: str  # in_review / screened_out / out_of_thesis
    application_id: int | None = None
    best_axis: str | None = None
    best_score: float | None = None
    scores: dict[str, float] = {}
    outreach_drafted: bool = False


class ScanSummaryOut(_ORM):
    sources_requested: list[str] = []
    source_errors: dict[str, str] = {}
    signals_fetched: int = 0
    signals_created: int = 0
    signals_duplicate: int = 0
    founders_created: int = 0
    companies_created: int = 0
    applications_created: int = 0
    outbound_in_review: int = 0
    outbound_screened_out: int = 0
    outreach_drafts: int = 0
    candidates: list[ScanCandidateOut] = []
