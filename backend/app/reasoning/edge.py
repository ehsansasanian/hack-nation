"""Edge panel (Phase 8) - the honest "why is this alpha" read.

A small, pure, deterministic function (no LLM, no network) that answers "why might
this application be alpha an incumbent tool would miss?" using ONLY data we already
store. Every line cites its own evidence - a flag, a field, or a signal - and the
whole thing is STRICTLY qualitative: no expected-return numbers, no fabricated
percentages, ever. Computed server-side so the read is consistent and traceable,
and folded into the application-detail response.

The four honestly-derivable edges:

* cold-start / pre-track-record - a founder scored on potential before any
  fundraising or press trail exists (cites the ``cold_start`` flag);
* outbound origin - sourced before the round (cites ``origin=outbound``);
* momentum - a per-axis ``trend=improving`` (direction, not just level);
* signal recency - the freshest evidence is recent and live (cites the signal).

When nothing is derivable the summary is empty and the caller renders an honest
"no distinct edge on file" note rather than inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_AXIS_LABEL = {
    "founder": "Founder",
    "market": "Market",
    "idea_vs_market": "Idea vs Market",
}


@dataclass(slots=True)
class EdgeLine:
    key: str  # stable id: cold_start | outbound | momentum | recency
    label: str  # short title
    detail: str  # qualitative explanation
    evidence: str  # the flag / field / signal it is derived from


@dataclass(slots=True)
class EdgeScore:
    """The minimal per-axis view compute_edge reads (kept ORM-agnostic)."""

    axis: str
    trend: str | None
    cold_start: bool
    confidence: float | None


@dataclass(slots=True)
class LatestSignal:
    id: int
    source: str
    timestamp: datetime


@dataclass(slots=True)
class Edge:
    lines: list[EdgeLine]
    summary: str  # one honest lead sentence; "" when no edge is derivable

    @property
    def has_edge(self) -> bool:
        return bool(self.lines)


def _cold_start_line(scores: list[EdgeScore]) -> EdgeLine | None:
    cs = next((s for s in scores if s.cold_start), None)
    if cs is None:
        return None
    conf = f", confidence {cs.confidence:.2f}" if cs.confidence is not None else ""
    return EdgeLine(
        key="cold_start",
        label="Pre-track-record founder",
        detail=(
            "Scored on potential before any funding round or press trail exists - "
            "exactly the founder an incumbent, database-driven tool has no row for yet. "
            "Thin evidence is handled as uncertainty, not a default-low score."
        ),
        evidence=f"cold_start flag on the {_AXIS_LABEL.get(cs.axis, cs.axis)} axis{conf}",
    )


def _outbound_line(origin: str) -> EdgeLine | None:
    if origin != "outbound":
        return None
    return EdgeLine(
        key="outbound",
        label="Sourced outbound, pre-fundraise",
        detail=(
            "Surfaced by our own scan before the founder was raising - not an inbound "
            "deck already sitting in every other fund's inbox."
        ),
        evidence="origin = outbound",
    )


def _momentum_line(scores: list[EdgeScore]) -> EdgeLine | None:
    improving = [s.axis for s in scores if (s.trend or "").lower() == "improving"]
    if not improving:
        return None
    names = ", ".join(_AXIS_LABEL.get(a, a) for a in improving)
    plural = "axes are" if len(improving) > 1 else "axis is"
    return EdgeLine(
        key="momentum",
        label="Positive momentum",
        detail=(
            f"The {names} {plural} trending up on the latest evidence - a read on "
            "direction and trajectory, not just the current level."
        ),
        evidence=f"trend = improving on {names}",
    )


def _recency_line(latest: LatestSignal | None) -> EdgeLine | None:
    if latest is None:
        return None
    when = latest.timestamp.date().isoformat()
    return EdgeLine(
        key="recency",
        label="Fresh signal trail",
        detail=(
            "The most recent evidence on file is a live-sourced signal, not a lagging "
            "filing or a stale database row that incumbents refresh on a quarterly cycle."
        ),
        evidence=f"latest signal #{latest.id} ({latest.source}, {when})",
    )


def compute_edge(
    *,
    origin: str,
    status: str,
    scores: list[EdgeScore],
    latest_signal: LatestSignal | None = None,
) -> Edge:
    """Derive the qualitative edge for one application from stored data only."""
    # Substantive edges - the ones that genuinely read as "alpha an incumbent misses".
    lines: list[EdgeLine] = [
        line
        for line in (
            _cold_start_line(scores),
            _outbound_line(origin),
            _momentum_line(scores),
        )
        if line is not None
    ]

    # Signal recency is a *supporting* line: it reinforces a real edge but never
    # stands alone claiming alpha (a screened-out app with a recent note is not alpha).
    if lines:
        recency = _recency_line(latest_signal)
        if recency is not None:
            lines.append(recency)

    if not lines:
        return Edge(lines=[], summary="")

    # An honest lead that names the strongest driver present; never a number.
    lead = {
        "cold_start": "Alpha from pre-track-record visibility - reasoning where incumbent tools have no data yet.",
        "outbound": "Alpha from proprietary sourcing - reached before the round opened.",
        "momentum": "Alpha from trajectory - the evidence is improving, not just present.",
        "recency": "Alpha from fresh, live signals rather than lagging filings.",
    }[lines[0].key]
    return Edge(lines=lines, summary=lead)


def edge_from_orm(application, latest_signal: LatestSignal | None = None) -> Edge:
    """Adapter: build an Edge from an ``Application`` ORM row and its scores."""
    scores = [
        EdgeScore(axis=s.axis, trend=s.trend, cold_start=bool(s.cold_start), confidence=s.confidence)
        for s in application.scores
    ]
    return compute_edge(
        origin=application.origin,
        status=application.status,
        scores=scores,
        latest_signal=latest_signal,
    )
