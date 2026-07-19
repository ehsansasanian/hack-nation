"""Core schema for The VC Brain.

Every model here maps 1:1 to the Phase 0 contract. The one addition beyond the
listed fields is ``Signal.last_seen``, required by the Phase 1 dedup rule
("on duplicate, keep earliest, update last_seen").
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    # Naive UTC everywhere so SQLite round-trips and dedup comparisons stay consistent.
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# A founder can start several companies; a company can have several founders.
founder_company = Table(
    "founder_company",
    Base.metadata,
    Column("founder_id", ForeignKey("founders.id", ondelete="CASCADE"), primary_key=True),
    Column("company_id", ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
)


class Founder(Base):
    __tablename__ = "founders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # normalized_name / github_handle back the entity-resolution lookups.
    normalized_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    github_handle: Mapped[str | None] = mapped_column(String, index=True)
    links: Mapped[dict] = mapped_column(JSON, default=dict)  # github/linkedin/twitter
    bio: Mapped[str | None] = mapped_column(Text)
    founder_score: Mapped[float | None] = mapped_column(Float)  # persistent, never resets
    score_history: Mapped[list] = mapped_column(JSON, default=list)  # [{timestamp, score, note}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    companies: Mapped[list["Company"]] = relationship(
        secondary=founder_company, back_populates="founders"
    )
    signals: Mapped[list["Signal"]] = relationship(back_populates="founder")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    domain: Mapped[str | None] = mapped_column(String, index=True)
    sector: Mapped[str | None] = mapped_column(String)
    stage: Mapped[str | None] = mapped_column(String)
    geography: Mapped[str | None] = mapped_column(String)
    one_liner: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    founders: Mapped[list["Founder"]] = relationship(
        secondary=founder_company, back_populates="companies"
    )
    signals: Mapped[list["Signal"]] = relationship(back_populates="company")
    applications: Mapped[list["Application"]] = relationship(back_populates="company")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    founder_id: Mapped[int | None] = mapped_column(ForeignKey("founders.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[str] = mapped_column(String, nullable=False)  # github/hn/deck/manual/synthetic
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # when it happened
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)  # when we saw it
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)  # touched on re-ingest
    dedup_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    founder: Mapped["Founder | None"] = relationship(back_populates="signals")
    company: Mapped["Company | None"] = relationship(back_populates="signals")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    deck_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="in_review")  # screened_out/in_review/memo_ready
    # Auto-analysis pipeline stage, driven by ``reasoning.analysis.analyze_application``.
    # received -> enriching -> screening -> scoring -> diligence -> memo -> ready, or the
    # terminal branches screened_out (chain honestly stopped at screening) / failed
    # (analysis_error set). ``enriching`` fetches self-declared founder links before screening.
    analysis_status: Mapped[str] = mapped_column(String, default="received")
    analysis_error: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String, default="inbound")  # inbound/outbound
    # Inbound enrichment: self-declared per-founder links collected on apply
    # ([{name, github, linkedin, website, x, other_links}]) and the per-source fetch
    # report the ``enriching`` stage records (source -> {outcome, signal_count}).
    declared_links: Mapped[list] = mapped_column(JSON, default=list)
    enrichment_report: Mapped[dict] = mapped_column(JSON, default=dict)
    # Screening (Phase 2 fast first-pass) verdict, stored for transparency - never silent.
    screening_verdict: Mapped[str | None] = mapped_column(String)  # viable/non_viable/thesis_mismatch
    screening_rationale: Mapped[str | None] = mapped_column(Text)
    # Outbound "Activate" step (Phase 3): a personalized draft outreach message.
    # Always a draft - nothing is ever sent anywhere.
    outreach_draft: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    company: Mapped["Company"] = relationship(back_populates="applications")
    scores: Mapped[list["Score"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    memo: Mapped["Memo | None"] = relationship(
        back_populates="application", cascade="all, delete-orphan", uselist=False
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False)
    axis: Mapped[str] = mapped_column(String, nullable=False)  # founder/market/idea_vs_market
    value: Mapped[float] = mapped_column(Float, nullable=False)  # 1-10 (range midpoint for cold-start)
    trend: Mapped[str | None] = mapped_column(String)  # improving/declining/stable
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_signal_ids: Mapped[list] = mapped_column(JSON, default=list)
    # Phase 2 additions: confidence, cold-start range + flag, and the model that produced this.
    confidence: Mapped[float | None] = mapped_column(Float)  # 0-1
    cold_start: Mapped[bool] = mapped_column(default=False)
    score_low: Mapped[float | None] = mapped_column(Float)  # set only on cold-start (range)
    score_high: Mapped[float | None] = mapped_column(Float)
    model: Mapped[str | None] = mapped_column(String)  # provenance: e.g. "gpt-4o" / "offline-deterministic"
    # Validator (self-correction) refutation of this axis rationale, if any. None =
    # the rationale survived the refutation pass.
    validator_note: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="scores")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String)  # traction/revenue/team/market
    # Where the claim originated (deck / twitter / blog / hn) - the head of the
    # signal -> claim -> trust -> memo chain Phase 6 traceability renders.
    source: Mapped[str | None] = mapped_column(String)
    trust_level: Mapped[str | None] = mapped_column(
        String
    )  # verified/consistent/unverified/contradicted
    evidence_signal_ids: Mapped[list] = mapped_column(JSON, default=list)
    contradiction_note: Mapped[str | None] = mapped_column(Text)
    # Validator (self-correction) outcome: a downgrade/confirmation note, stored so
    # the reasoning chain stays auditable. None = validator left the claim as-is.
    validator_note: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="claims")


class Thesis(Base):
    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sectors: Mapped[list] = mapped_column(JSON, default=list)
    stages: Mapped[list] = mapped_column(JSON, default=list)
    geographies: Mapped[list] = mapped_column(JSON, default=list)
    check_size: Mapped[str | None] = mapped_column(String)
    ownership_target: Mapped[str | None] = mapped_column(String)
    risk_appetite: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(default=True)


class Memo(Base):
    __tablename__ = "memos"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False)
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str | None] = mapped_column(String)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    application: Mapped["Application"] = relationship(back_populates="memo")
