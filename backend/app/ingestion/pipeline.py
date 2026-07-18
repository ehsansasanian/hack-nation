"""The single ingestion entry point every signal passes through.

Flow: normalize -> dedup (hash of source + canonical content key) -> entity
resolution (founder/company by github handle / normalized name / domain) ->
persist with both ``timestamp`` (event time) and ``ingested_at`` (observation
time). Live scrapers (Phase 3) and the synthetic loader (Phase 1) both call
``ingest_signal`` - there is no second path into the store.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Founder, Signal


@dataclass(slots=True)
class FounderHint:
    """Entity-resolution hint for the founder behind a signal."""

    name: str | None = None
    github_handle: str | None = None
    links: dict = field(default_factory=dict)
    bio: str | None = None
    founder_score: float | None = None
    score_history: list = field(default_factory=list)


@dataclass(slots=True)
class CompanyHint:
    """Entity-resolution hint for the company behind a signal."""

    name: str | None = None
    domain: str | None = None
    sector: str | None = None
    stage: str | None = None
    geography: str | None = None
    one_liner: str | None = None


@dataclass(slots=True)
class RawSignal:
    """A source-agnostic signal before it becomes a persisted ``Signal`` row."""

    source: str
    content: dict
    timestamp: datetime
    dedup_key: str | None = None  # stable content key; falls back to canonical JSON
    founder: FounderHint | None = None
    company: CompanyHint | None = None


def normalize_name(name: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace - the entity-match key."""
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _canonical_key(raw: RawSignal) -> str:
    if raw.dedup_key:
        return raw.dedup_key
    return json.dumps(raw.content, sort_keys=True, default=str)


def _dedup_hash(source: str, canonical_key: str) -> str:
    return hashlib.sha256(f"{source}::{canonical_key}".encode()).hexdigest()


def _resolve_founder(session: Session, hint: FounderHint | None) -> Founder | None:
    if hint is None or not (hint.name or hint.github_handle):
        return None
    founder: Founder | None = None
    if hint.github_handle:
        founder = session.scalar(
            select(Founder).where(Founder.github_handle == hint.github_handle)
        )
    if founder is None and hint.name:
        founder = session.scalar(
            select(Founder).where(Founder.normalized_name == normalize_name(hint.name))
        )
    if founder is None:
        display = hint.name or hint.github_handle or ""
        founder = Founder(
            name=display,
            normalized_name=normalize_name(display),
            github_handle=hint.github_handle,
            links=dict(hint.links),
            bio=hint.bio,
            founder_score=hint.founder_score,
            score_history=list(hint.score_history),
        )
        session.add(founder)
        session.flush()
    else:
        _enrich_founder(founder, hint)
    return founder


def _enrich_founder(founder: Founder, hint: FounderHint) -> None:
    """Fill gaps on an existing founder without clobbering known values."""
    if hint.github_handle and not founder.github_handle:
        founder.github_handle = hint.github_handle
    if hint.bio and not founder.bio:
        founder.bio = hint.bio
    if hint.links:
        founder.links = {**hint.links, **(founder.links or {})}
    if hint.founder_score is not None and founder.founder_score is None:
        founder.founder_score = hint.founder_score
    if hint.score_history and not founder.score_history:
        founder.score_history = list(hint.score_history)


def _resolve_company(session: Session, hint: CompanyHint | None) -> Company | None:
    if hint is None or not (hint.name or hint.domain):
        return None
    company: Company | None = None
    if hint.domain:
        company = session.scalar(select(Company).where(Company.domain == hint.domain))
    if company is None and hint.name:
        company = session.scalar(
            select(Company).where(Company.normalized_name == normalize_name(hint.name))
        )
    if company is None:
        display = hint.name or hint.domain or ""
        company = Company(
            name=display,
            normalized_name=normalize_name(display),
            domain=hint.domain,
            sector=hint.sector,
            stage=hint.stage,
            geography=hint.geography,
            one_liner=hint.one_liner,
        )
        session.add(company)
        session.flush()
    else:
        _enrich_company(company, hint)
    return company


def _enrich_company(company: Company, hint: CompanyHint) -> None:
    for attr in ("domain", "sector", "stage", "geography", "one_liner"):
        if getattr(company, attr) is None and getattr(hint, attr) is not None:
            setattr(company, attr, getattr(hint, attr))


def ingest_signal(session: Session, raw: RawSignal) -> tuple[Signal, bool]:
    """Ingest one signal. Returns ``(signal, created)``.

    On a dedup hit the existing row is kept: the earliest event ``timestamp`` is
    preserved and ``last_seen`` is bumped. No new row is written.
    """
    canonical_key = _canonical_key(raw)
    dedup_hash = _dedup_hash(raw.source, canonical_key)
    event_ts = _naive_utc(raw.timestamp)

    existing = session.scalar(select(Signal).where(Signal.dedup_hash == dedup_hash))
    if existing is not None:
        if event_ts < existing.timestamp:
            existing.timestamp = event_ts
        existing.last_seen = datetime.now(UTC).replace(tzinfo=None)
        return existing, False

    founder = _resolve_founder(session, raw.founder)
    company = _resolve_company(session, raw.company)
    if founder is not None and company is not None and company not in founder.companies:
        founder.companies.append(company)

    signal = Signal(
        founder_id=founder.id if founder else None,
        company_id=company.id if company else None,
        source=raw.source,
        content=raw.content,
        timestamp=event_ts,
        dedup_hash=dedup_hash,
    )
    session.add(signal)
    session.flush()
    return signal, True
