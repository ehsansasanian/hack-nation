"""Persistent Founder Score updater.

The Founder Score is memory: it never resets. After each scoring run the new
founder-axis evidence is blended into the standing score and a timestamped entry
is appended to ``score_history``. The blend is confidence-weighted, so a
low-confidence cold-start read nudges the score only slightly. Trend is derived
from the history, never stored as a raw input.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Founder

_BASE_ALPHA = 0.5  # max weight a single new reading can take, before confidence scaling


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def update_founder_score(
    founder: Founder,
    evidence_score: float,
    confidence: float,
    cold_start: bool,
    application_id: int,
    company_name: str,
) -> tuple[float, str]:
    """Blend ``evidence_score`` into ``founder.founder_score`` and log history.

    Returns ``(new_score, trend)``. ``trend`` compares the new standing score to
    the previous one (from history), yielding improving/declining/stable.
    """
    old = founder.founder_score
    if old is None:
        new_score = round(evidence_score, 2)  # establish the baseline
    else:
        alpha = round(_BASE_ALPHA * confidence, 3)
        new_score = round(alpha * evidence_score + (1 - alpha) * old, 2)

    trend = _trend(old, new_score)

    entry = {
        "timestamp": _now_iso(),
        "score": new_score,
        "evidence_score": round(evidence_score, 2),
        "confidence": round(confidence, 2),
        "cold_start": cold_start,
        "application_id": application_id,
        "note": f"scored via application {application_id} ({company_name})",
    }
    # Reassign (not append) so SQLAlchemy detects the JSON column mutation.
    founder.score_history = list(founder.score_history or []) + [entry]
    founder.founder_score = new_score
    return new_score, trend


def _trend(old: float | None, new: float) -> str:
    if old is None:
        return "stable"
    if new > old + 0.2:
        return "improving"
    if new < old - 0.2:
        return "declining"
    return "stable"
