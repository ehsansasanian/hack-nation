"""Assemble the evidence context each scoring call reasons over.

One place gathers the signals, splits them into the per-axis evidence universes,
and detects the cold-start condition - so backends only consume a prepared
``ScoringContext`` and never touch the ORM directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Company, Founder, Signal, Thesis
from app.reasoning.mandate import axis_note, render_guidance

# A founder with any of these has a track record - not a cold start.
TRACK_RECORD_SOURCES = {"github", "hn"}
GRADUATED_STAGES = {"acquired", "seed", "series-a", "series-b", "series-c", "growth"}


@dataclass(slots=True)
class ScoringContext:
    application: Application
    company: Company
    founders: list[Founder]  # the full team, primary first
    founder_signals: list[Signal]  # across all the founders' companies (persistent view)
    company_signals: list[Signal]  # this company only
    deck_text: str
    thesis_rationale: str
    cold_start: bool  # team-level: True only when EVERY founder is individually cold-start
    # Per-founder groupings for team-complementarity reasoning (founder_id -> ...).
    founder_signal_groups: dict[int, list[Signal]] = field(default_factory=dict)
    founder_cold_start: dict[int, bool] = field(default_factory=dict)
    # Phase 8 fund guidelines injected into the screening + axis prompts.
    mandate_guidance: str = ""  # free-text principles + curated constraints
    axis_notes: dict[str, str] = field(default_factory=dict)  # per-axis emphasis notes

    # Per-axis evidence universes: the ids the model is allowed to cite.
    def founder_evidence_ids(self) -> set[int]:
        return {s.id for s in self.founder_signals}

    def signals_for(self, founder_id: int) -> list[Signal]:
        return self.founder_signal_groups.get(founder_id, [])

    @property
    def is_team(self) -> bool:
        return len(self.founders) > 1

    def market_evidence_ids(self) -> set[int]:
        return {s.id for s in self.company_signals}

    def idea_evidence_ids(self) -> set[int]:
        return {s.id for s in self.company_signals}


def _render_signal(sig: Signal) -> str:
    content = json.dumps(sig.content, sort_keys=True, default=str)
    when = sig.timestamp.date().isoformat()
    return f"[signal_id={sig.id}] source={sig.source} date={when} {content}"


def render_signals(signals: list[Signal]) -> str:
    if not signals:
        return "(no signals available)"
    return "\n".join(_render_signal(s) for s in sorted(signals, key=lambda s: s.timestamp))


def detect_cold_start(founder: Founder | None, founder_signals: list[Signal]) -> bool:
    """A cold-start founder: no external track record to score against.

    Detection is intentionally based on *stable* facts (companies, external
    signals, prior graduated stage) rather than the founder_score we ourselves
    write - so a re-run never silently flips the flag off.
    """
    if founder is None:
        return True
    if len(founder.companies) > 1:
        return False
    if any(s.source in TRACK_RECORD_SOURCES for s in founder_signals):
        return False
    if any((c.stage or "").lower() in GRADUATED_STAGES for c in founder.companies):
        return False
    return True


def _norm_gh(value: str | None) -> str | None:
    """Minimal GitHub-handle normaliser (avoids importing the sourcing http stack)."""
    if not value:
        return None
    v = value.strip().rstrip("/")
    if "github.com/" in v:
        v = v.split("github.com/", 1)[-1].split("/", 1)[0]
    v = v.lstrip("@").strip().lower()
    return v or None


def _links_from(rec: dict) -> dict:
    links = {}
    for key in ("github", "linkedin", "website", "x"):
        if rec.get(key):
            links[key] = rec[key]
    return links


def _resolve_declared_founders(
    session: Session, application: Application, create: bool
) -> list[Founder]:
    """Resolve each declared co-founder to a Founder row (by github handle / name).

    ``create=True`` also creates a link-less co-founder that is not yet in Memory and
    attaches nothing here - so every declared founder becomes a first-class Founder
    (a co-founder already in Memory resolves to their prior history + persistent
    Founder Score). ``create=False`` is a pure read (resolve existing only), so read
    paths like the trace never write.
    """
    resolved: list[Founder] = []
    seen: set[int] = set()
    for rec in application.declared_links or []:
        if not isinstance(rec, dict):
            continue
        gh = _norm_gh(rec.get("github"))
        name = (rec.get("name") or "").strip() or None
        founder: Founder | None = None
        if gh:
            founder = session.scalar(select(Founder).where(Founder.github_handle == gh))
        if founder is None and name:
            founder = session.scalar(
                select(Founder).where(Founder.normalized_name == _normalize_name(name))
            )
        if founder is None and create and name:
            founder = Founder(
                name=name,
                normalized_name=_normalize_name(name),
                github_handle=gh,
                links=_links_from(rec),
                bio=(rec.get("bio") or None),
                score_history=[],
            )
            session.add(founder)
            session.flush()
        if founder is not None and founder.id not in seen:
            seen.add(founder.id)
            resolved.append(founder)
    return resolved


def _normalize_name(name: str) -> str:
    import re

    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def ensure_team_resolved(session: Session, application: Application) -> list[Founder]:
    """Attach every declared co-founder to the company (idempotent; write path only).

    Enrichment fetches each founder's links into founder-scoped signals but leaves the
    company link to the primary; this makes every declared co-founder a first-class
    member of ``company.founders`` so the founder axis can evaluate the whole team and
    the persistent Founder Score updates for each of them. Caller commits.
    """
    company = application.company
    for f in _resolve_declared_founders(session, application, create=True):
        if company not in f.companies:
            f.companies.append(company)
    session.flush()
    return _ordered_team(session, application, company)


def _ordered_team(
    session: Session, application: Application, company: Company
) -> list[Founder]:
    """The full team, primary (declared_links[0]) first, then remaining attached."""
    attached = list(company.founders)
    declared = _resolve_declared_founders(session, application, create=False)
    if not declared:
        return attached
    ordered: list[Founder] = []
    for f in declared + attached:
        if f not in ordered:
            ordered.append(f)
    return ordered


def build_context(
    session: Session,
    application: Application,
    thesis_rationale: str,
    thesis: Thesis | None = None,
) -> ScoringContext:
    company = application.company
    founders = _ordered_team(session, application, company)
    founder_ids = [f.id for f in founders]

    company_signals = list(
        session.scalars(
            select(Signal)
            .where(Signal.company_id == company.id)
            .options(selectinload(Signal.company))
        ).all()
    )

    if founder_ids:
        founder_signals = list(
            session.scalars(
                select(Signal).where(
                    or_(
                        Signal.founder_id.in_(founder_ids),
                        Signal.company_id == company.id,
                    )
                )
            ).all()
        )
    else:
        founder_signals = list(company_signals)

    # Group the persistent founder view per founder for team-complementarity reasoning.
    # A signal attributed to a founder (founder_id) travels with that founder across
    # every company they have backed; company-only signals stay ungrouped (market side).
    founder_signal_groups: dict[int, list[Signal]] = {f.id: [] for f in founders}
    for s in founder_signals:
        if s.founder_id in founder_signal_groups:
            founder_signal_groups[s.founder_id].append(s)

    # Per-founder cold-start, then the team-level flag: a team is only cold-start when
    # EVERY founder is individually cold-start (one founder with a track record does
    # not zero a co-founder who is cold-start, and vice versa).
    founder_cold_start = {
        f.id: detect_cold_start(f, founder_signal_groups.get(f.id, [])) for f in founders
    }
    if founders:
        cold_start = all(founder_cold_start[f.id] for f in founders)
    else:
        cold_start = detect_cold_start(None, founder_signals)

    return ScoringContext(
        application=application,
        company=company,
        founders=founders,
        founder_signals=founder_signals,
        company_signals=company_signals,
        deck_text=application.deck_text or "",
        thesis_rationale=thesis_rationale,
        cold_start=cold_start,
        founder_signal_groups=founder_signal_groups,
        founder_cold_start=founder_cold_start,
        mandate_guidance=render_guidance(thesis),
        axis_notes={
            axis: axis_note(thesis, axis)
            for axis in ("founder", "market", "idea_vs_market")
            if axis_note(thesis, axis)
        },
    )
