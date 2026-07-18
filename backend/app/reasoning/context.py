"""Assemble the evidence context each scoring call reasons over.

One place gathers the signals, splits them into the per-axis evidence universes,
and detects the cold-start condition - so backends only consume a prepared
``ScoringContext`` and never touch the ORM directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Company, Founder, Signal

# A founder with any of these has a track record - not a cold start.
TRACK_RECORD_SOURCES = {"github", "hn"}
GRADUATED_STAGES = {"acquired", "seed", "series-a", "series-b", "series-c", "growth"}


@dataclass(slots=True)
class ScoringContext:
    application: Application
    company: Company
    founders: list[Founder]
    founder_signals: list[Signal]  # across all the founders' companies (persistent view)
    company_signals: list[Signal]  # this company only
    deck_text: str
    thesis_rationale: str
    cold_start: bool

    # Per-axis evidence universes: the ids the model is allowed to cite.
    def founder_evidence_ids(self) -> set[int]:
        return {s.id for s in self.founder_signals}

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


def build_context(
    session: Session, application: Application, thesis_rationale: str
) -> ScoringContext:
    company = application.company
    founders = list(company.founders)
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

    # A founder can back several companies; the persistent founder view spans them.
    primary = founders[0] if founders else None
    cold_start = detect_cold_start(primary, founder_signals)

    return ScoringContext(
        application=application,
        company=company,
        founders=founders,
        founder_signals=founder_signals,
        company_signals=company_signals,
        deck_text=application.deck_text or "",
        thesis_rationale=thesis_rationale,
        cold_start=cold_start,
    )
