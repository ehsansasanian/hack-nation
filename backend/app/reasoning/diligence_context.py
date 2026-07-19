"""Assemble the evidence context the diligence backends reason over (Phase 4).

Mirrors ``reasoning/context.py``. One place gathers the signals and splits them
into two roles so both backends agree on what is a *claim source* and what is
*evidence*:

* claim sources: things the company/founder asserts about themselves - the deck
  plus self-asserted public posts (twitter / blog / Show HN). These are what we
  diligence.
* evidence: everything we can check a claim against - private diligence notes
  (``manual``) and objective metrics (``github`` stars, ``hn`` points).

Backends only ever consume a prepared ``DiligenceContext`` and never touch the
ORM, exactly like the scoring seam.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Application, Company, Founder, Signal
from app.reasoning.context import build_context

# Sources whose text is a self-asserted claim (vs objective evidence). The deck is
# always a claim source; these are the public-post equivalents.
SELF_ASSERTED_SOURCES = {"twitter", "blog"}
# Sources that count as checkable evidence for the truth-gap. ``web`` is here because
# it is *externally fetched* website content (facts extracted from a real page), so
# it can verify or contradict a deck claim. Self-declared-but-unfetched references
# (linkedin / x, recorded ``blocked``) are deliberately NOT evidence - they can lift
# nothing beyond ``unverified``.
EVIDENCE_SOURCES = {"manual", "github", "hn", "web"}


@dataclass(slots=True)
class ClaimSource:
    """A block of self-asserted text a claim can be extracted from."""

    source: str  # deck / twitter / blog / hn
    text: str
    signal_id: int | None = None  # None for the deck (it is not a Signal row)


@dataclass(slots=True)
class DiligenceContext:
    application: Application
    company: Company
    founders: list[Founder]
    deck_text: str
    claim_sources: list[ClaimSource]
    evidence_signals: list[Signal]
    scores: list[Score] = field(default_factory=list)
    thesis_rationale: str = ""
    cold_start: bool = False

    def evidence_ids(self) -> set[int]:
        return {s.id for s in self.evidence_signals}


def render_evidence(signals: list[Signal]) -> str:
    """One line per evidence signal, ids included so a backend can cite them."""
    if not signals:
        return "(no evidence signals available)"
    lines = []
    for s in sorted(signals, key=lambda s: s.timestamp):
        body = json.dumps(s.content, sort_keys=True, default=str)
        lines.append(f"[signal_id={s.id}] source={s.source} date={s.timestamp.date().isoformat()} {body}")
    return "\n".join(lines)


def _self_asserted_text(sig: Signal) -> str:
    """Human-readable assertion text from a self-asserted signal's content."""
    c = sig.content
    for key in ("text", "summary", "title", "note"):
        if c.get(key):
            return str(c[key])
    return json.dumps(c, default=str)


def build_diligence_context(
    session: Session,
    application: Application,
    thesis_rationale: str = "",
) -> DiligenceContext:
    # Reuse the scoring context so signal gathering + cold-start detection stay
    # identical across the two reasoning layers.
    sc = build_context(session, application, thesis_rationale)
    all_signals = list({s.id: s for s in (sc.company_signals + sc.founder_signals)}.values())

    claim_sources: list[ClaimSource] = []
    if sc.deck_text.strip():
        claim_sources.append(ClaimSource(source="deck", text=sc.deck_text))
    for sig in all_signals:
        if sig.source in SELF_ASSERTED_SOURCES:
            text = _self_asserted_text(sig)
            if text.strip():
                claim_sources.append(ClaimSource(source=sig.source, text=text, signal_id=sig.id))

    evidence_signals = [s for s in all_signals if s.source in EVIDENCE_SOURCES]

    return DiligenceContext(
        application=application,
        company=sc.company,
        founders=sc.founders,
        deck_text=sc.deck_text,
        claim_sources=claim_sources,
        evidence_signals=evidence_signals,
        scores=list(application.scores),
        thesis_rationale=thesis_rationale,
        cold_start=sc.cold_start,
    )
