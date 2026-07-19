"""Founders directory + team matching (Phase 8 - the Database tab).

A thin, deterministic layer over the EXISTING complementarity engine - it never
rebuilds any of it:

* classification (technical / commercial) is ``team.founder_is_technical`` /
  ``team.founder_is_commercial`` - the same read the offline scoring backend and
  the memo use, so the Database tab never disagrees with them;
* the pair verdict + lift come straight from ``team.assess_team``;
* availability and the "find complementary founders" shortlist reuse the
  recombination module's availability rule and candidate ranker.

$0 LLM: everything here is offline and deterministic (the recombination narrative
that an LLM can write is NOT invoked - the Database tab only needs the shortlist
and the deterministic verdict). Read-only: nothing here mutates a Score, a
Founder Score, or any application assessment. A match is explicitly HYPOTHETICAL.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Company, Founder, Thesis
from app.reasoning.recombination import (
    Candidate,
    _availability,
    _founder_sectors,
    _rank_candidates,
    _team_needs,
)
from app.reasoning.team import (
    TeamAssessment,
    assess_team,
    founder_is_commercial,
    founder_is_technical,
    patterns_tag,
)

# Sectors that structurally need a technical founder (mirrors team._DEEPTECH_SECTORS).
from app.reasoning.team import _DEEPTECH_SECTORS


def classify(technical: bool, commercial: bool) -> str:
    if technical and commercial:
        return "technical + commercial"
    if technical:
        return "technical"
    if commercial:
        return "commercial"
    return "unclassified"


def _domain(founder: Founder) -> str | None:
    return ", ".join(sorted(s for s in _founder_sectors(founder) if s)) or None


def _primary_sector(founder: Founder) -> str | None:
    """A representative sector for a founder (first company that names one)."""
    for c in founder.companies:
        if c.sector:
            return c.sector
    return None


# --- directory ---------------------------------------------------------------


@dataclass(slots=True)
class DirectoryFounder:
    id: int
    name: str
    github_handle: str | None
    founder_score: float | None
    technical: bool
    commercial: bool
    classification: str
    domain: str | None
    available: bool
    availability: str  # human-readable reason (recombination availability rule)
    returning: bool  # track record across more than one company


def list_founders(session: Session, thesis: Thesis | None) -> list[DirectoryFounder]:
    """Every founder in Memory with classification, availability and the returning marker."""
    founders = list(
        session.scalars(
            select(Founder)
            .options(
                selectinload(Founder.companies).selectinload(Company.applications),
                selectinload(Founder.signals),
            )
            .order_by(Founder.name)
        ).all()
    )
    out: list[DirectoryFounder] = []
    for f in founders:
        technical = founder_is_technical(f, list(f.signals))
        commercial = founder_is_commercial(f)
        available, label = _availability(f, thesis)
        out.append(
            DirectoryFounder(
                id=f.id,
                name=f.name,
                github_handle=f.github_handle,
                founder_score=f.founder_score,
                technical=technical,
                commercial=commercial,
                classification=classify(technical, commercial),
                domain=_domain(f),
                available=available,
                availability=label,
                returning=len(f.companies) > 1,
            )
        )
    return out


# --- pairwise match ----------------------------------------------------------


@dataclass(slots=True)
class MatchFounder:
    id: int
    name: str
    github_handle: str | None
    founder_score: float | None
    technical: bool
    commercial: bool
    classification: str
    domain: str | None
    available: bool
    availability: str


def _match_founder(session: Session, founder: Founder, thesis: Thesis | None) -> MatchFounder:
    technical = founder_is_technical(founder, list(founder.signals))
    commercial = founder_is_commercial(founder)
    available, label = _availability(founder, thesis)
    return MatchFounder(
        id=founder.id,
        name=founder.name,
        github_handle=founder.github_handle,
        founder_score=founder.founder_score,
        technical=technical,
        commercial=commercial,
        classification=classify(technical, commercial),
        domain=_domain(founder),
        available=available,
        availability=label,
    )


@dataclass(slots=True)
class MatchResult:
    founder_a: MatchFounder
    founder_b: MatchFounder
    sector: str | None
    solo: bool
    technical: bool
    commercial: bool
    complementary: bool
    domain_gap: bool
    prior_collab: bool
    verdict: str
    lift: float
    gaps: list[str]
    patterns: str
    rationale: str
    hypothetical_team: str


def _load_founder(session: Session, founder_id: int) -> Founder:
    founder = session.get(
        Founder,
        founder_id,
        options=[
            selectinload(Founder.companies).selectinload(Company.applications),
            selectinload(Founder.signals),
        ],
    )
    if founder is None:
        raise LookupError(f"Founder {founder_id} not found.")
    return founder


def _match_sector(a: Founder, b: Founder) -> str | None:
    """A sector to anchor the pair's domain-gap read.

    Prefer a deep-tech sector either founder has worked in (so a pairing of two
    non-technical founders in a deep-tech domain is honestly flagged); otherwise
    fall back to the primary founder's sector.
    """
    sectors = sorted(_founder_sectors(a) | _founder_sectors(b))  # sorted = deterministic
    for s in sectors:
        if s in _DEEPTECH_SECTORS:
            return s
    return _primary_sector(a) or _primary_sector(b)


def _bring(f: MatchFounder) -> str:
    if f.technical and f.commercial:
        return "technical depth plus commercial/GTM coverage"
    if f.technical:
        return "technical depth"
    if f.commercial:
        return "commercial/GTM coverage"
    return "domain expertise"


def match_founders(
    session: Session, founder_a_id: int, founder_b_id: int, thesis: Thesis | None
) -> MatchResult:
    """Run the EXISTING team-complementarity assessment on a hypothetical pairing."""
    if founder_a_id == founder_b_id:
        raise ValueError("Pick two different founders to assess a team.")
    fa = _load_founder(session, founder_a_id)
    fb = _load_founder(session, founder_b_id)

    sector = _match_sector(fa, fb)
    signals_by_founder = {fa.id: list(fa.signals), fb.id: list(fb.signals)}
    team: TeamAssessment = assess_team([fa, fb], signals_by_founder, sector)

    a = _match_founder(session, fa, thesis)
    b = _match_founder(session, fb, thesis)
    complementary = team.technical and team.commercial
    prior_exit = any((c.stage or "").lower() == "acquired" for c in fa.companies + fb.companies)
    patterns = patterns_tag(fa, team, prior_exit)

    gaps_txt = "; ".join(team.gaps) if team.gaps else "no structural coverage gap identified"
    patterns_clause = f"; {patterns.rstrip('.')}" if patterns else ""
    rationale = (
        f"Hypothetical pairing of {a.name} ({a.classification}) and "
        f"{b.name} ({b.classification})"
        + (f", anchored on the {sector} domain. " if sector else ". ")
        + f"{team.verdict.capitalize()}. "
        f"{a.name} brings {_bring(a)}; {b.name} brings {_bring(b)}. "
        f"Complementarity lift {team.lift:+} to the founder axis"
        + patterns_clause
        + f". Gaps: {gaps_txt}. "
        "This is a HYPOTHETICAL team read - it changes neither founder's persistent "
        "score nor any application's assessment."
    )
    hypothetical_team = f"Hypothetical team: {a.name} + {b.name} - {team.verdict}"

    return MatchResult(
        founder_a=a,
        founder_b=b,
        sector=sector,
        solo=team.solo,
        technical=team.technical,
        commercial=team.commercial,
        complementary=complementary,
        domain_gap=team.domain_gap,
        prior_collab=team.prior_collab,
        verdict=team.verdict,
        lift=team.lift,
        gaps=team.gaps,
        patterns=patterns,
        rationale=rationale,
        hypothetical_team=hypothetical_team,
    )


# --- "find matches" for one founder ------------------------------------------


@dataclass(slots=True)
class MatchesResult:
    founder: MatchFounder
    needs: list[str]
    candidates: list[Candidate]


def matches_for(session: Session, founder_id: int, thesis: Thesis | None) -> MatchesResult:
    """Shortlist complementary, available founders for one founder.

    Reuses the recombination candidate ranker: treat the founder as a team of one,
    compute the coverage they are missing, and rank available Memory founders that
    would close it. Deterministic and $0 LLM.
    """
    founder = _load_founder(session, founder_id)
    mf = _match_founder(session, founder, thesis)
    sector = _primary_sector(founder)
    domain_gap = (sector or "").strip().lower() in _DEEPTECH_SECTORS and not mf.technical
    needs = _team_needs(mf.technical, mf.commercial, domain_gap, solo=True)
    candidates = _rank_candidates(session, {founder.id}, sector, needs, thesis)
    return MatchesResult(founder=mf, needs=sorted(needs), candidates=candidates)
