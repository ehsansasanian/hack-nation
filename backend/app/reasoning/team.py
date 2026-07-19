"""Team-complementarity assessment (Phase 8).

Complementarity is an INPUT to the existing founder axis - never a fourth axis (the
brief fixes three). This module is the single, deterministic source of truth for the
team read, shared by the offline scoring backend (so its numbers are defensible) and
by the memo's "Team & history" section (so the memo and the score agree). The OpenAI
backend reasons over the same rubric in prose.

The read: per-founder technical vs commercial coverage, domain gaps relative to the
idea, prior-collaboration signal, and the solo-founder case - which is always a
*flagged risk with rationale*, never an automatic penalty.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Founder, Signal

_TECH_KW = (
    "engineer", "engineering", "cto", " ml", "machine learning", "phd", "infra",
    "infrastructure", "developer", "backend", "systems", "researcher", "research",
    "built", "compiler", "kernel", "ex-deepmind", "hacker", "inference",
)
_COMM_KW = (
    "ceo", "sales", "gtm", "go-to-market", "business", "commercial", "growth",
    "marketing", "operations", "bd", "partnerships", "product manager", " pm", "operator",
    "finance", "revenue", "customer",
)
# Ideas that structurally need a technical founder; no technical founder = explicit gap.
_DEEPTECH_SECTORS = ("ai infra", "devtools", "robotics", "security", "health", "fintech")
_COLLAB_KW = (
    "co-founded", "cofounded", "built together", "worked together", "same team",
    "previously together", "ex-teammates", "second company together", "founded together",
)


def _hits(blob: str, terms: tuple[str, ...]) -> bool:
    return any(t in blob for t in terms)


@dataclass(slots=True)
class TeamAssessment:
    solo: bool
    technical: bool
    commercial: bool
    domain_gap: bool  # deep-tech idea with no technical founder
    prior_collab: bool
    verdict: str
    lift: float  # complementarity adjustment to the founder axis (team only)
    evidence: list[int]
    gaps: list[str]


def founder_is_technical(founder: Founder, signals: list[Signal]) -> bool:
    if founder.github_handle or any(s.source == "github" for s in signals):
        return True
    return _hits((founder.bio or "").lower(), _TECH_KW)


def founder_is_commercial(founder: Founder) -> bool:
    return _hits((founder.bio or "").lower(), _COMM_KW)


def assess_team(
    founders: list[Founder],
    signals_by_founder: dict[int, list[Signal]],
    sector: str | None,
) -> TeamAssessment:
    solo = len(founders) <= 1
    technical = any(founder_is_technical(f, signals_by_founder.get(f.id, [])) for f in founders)
    commercial = any(founder_is_commercial(f) for f in founders)
    sec = (sector or "").lower()
    domain_gap = sec in _DEEPTECH_SECTORS and not technical
    bios = " ".join((f.bio or "") for f in founders).lower()
    prior_collab = _hits(bios, _COLLAB_KW)
    evidence: list[int] = []
    for f in founders:
        evidence += [s.id for s in signals_by_founder.get(f.id, [])]

    lift = 0.0
    gaps: list[str] = []
    if solo:
        verdict = "solo founder - flagged risk (no automatic penalty)"
        gaps.append("single founder - no co-founder coverage or prior-collaboration signal")
    elif technical and commercial:
        verdict = "complementary team - technical and commercial ground both covered"
        lift += 0.6
    elif technical and not commercial:
        verdict = "technical-heavy team - commercial/GTM coverage is a gap"
        lift += 0.1
        gaps.append("no clear commercial/GTM founder")
    elif commercial and not technical:
        verdict = "commercial-led team - technical coverage is a gap"
        lift -= 0.3 if domain_gap else 0.0
        gaps.append("no clear technical founder")
    else:
        verdict = "coverage unclear from the evidence on file"
        gaps.append("neither technical nor commercial coverage is evident")
    if domain_gap and not solo:
        verdict += "; deep-tech idea with no technical founder is an explicit team gap"
        gaps.append(f"{sec} idea with no technical founder")
    if prior_collab:
        verdict += "; prior-collaboration signal present"
        lift += 0.3
    return TeamAssessment(
        solo=solo, technical=technical, commercial=commercial, domain_gap=domain_gap,
        prior_collab=prior_collab, verdict=verdict, lift=round(lift, 2),
        evidence=sorted(set(evidence)), gaps=gaps,
    )


def patterns_tag(founder: Founder | None, team: TeamAssessment, prior_exit: bool) -> str:
    """Cite the research-backed founder-success patterns actually in play."""
    hits = []
    if prior_exit or (founder and len(founder.companies) > 1):
        hits.append("serial-founder premium")
    if team.technical:
        hits.append("technical-founder effect")
    if not team.solo:
        hits.append("team complementarity")
    return ("patterns: " + ", ".join(hits) + ".") if hits else ""
