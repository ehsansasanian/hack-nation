"""Founder endpoints: profile, directory listing, and team matching.

The directory + matching endpoints back the Database tab. They reuse the existing
complementarity engine (``app.reasoning.matching`` -> ``team`` / ``recombination``)
and are fully deterministic and $0 LLM.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Founder, Thesis
from app.reasoning.matching import list_founders, match_founders, matches_for
from app.schemas import (
    DirectoryFounderOut,
    FounderDetailOut,
    FounderMatchesOut,
    FounderMatchOut,
    FounderMatchRequest,
    MatchFounderOut,
    RecombinationCandidateOut,
)

router = APIRouter(tags=["founders"])


def _active_thesis(session: Session) -> Thesis | None:
    return session.scalar(select(Thesis).order_by(Thesis.id.desc()))


@router.get("/founders", response_model=list[DirectoryFounderOut])
def list_founders_endpoint(
    session: Session = Depends(get_session),
) -> list[DirectoryFounderOut]:
    """The founders directory: every founder in Memory with classification
    (technical/commercial), domain, availability (not tied to an active in-thesis
    application) and the returning-founder marker. Deterministic, no LLM."""
    thesis = _active_thesis(session)
    return [DirectoryFounderOut(**asdict(f)) for f in list_founders(session, thesis)]


@router.post("/founders/match", response_model=FounderMatchOut)
def match_founders_endpoint(
    payload: FounderMatchRequest,
    session: Session = Depends(get_session),
) -> FounderMatchOut:
    """Run the existing team-complementarity assessment on a HYPOTHETICAL pairing
    of two founders and return the verdict + rationale + hypothetical-team framing.
    Deterministic offline path only - never changes any real score."""
    thesis = _active_thesis(session)
    try:
        result = match_founders(session, payload.founder_a, payload.founder_b, thesis)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FounderMatchOut(
        founder_a=MatchFounderOut(**asdict(result.founder_a)),
        founder_b=MatchFounderOut(**asdict(result.founder_b)),
        sector=result.sector,
        solo=result.solo,
        technical=result.technical,
        commercial=result.commercial,
        complementary=result.complementary,
        domain_gap=result.domain_gap,
        prior_collab=result.prior_collab,
        verdict=result.verdict,
        lift=result.lift,
        gaps=result.gaps,
        patterns=result.patterns,
        rationale=result.rationale,
        hypothetical_team=result.hypothetical_team,
    )


@router.get("/founders/{founder_id}/matches", response_model=FounderMatchesOut)
def founder_matches_endpoint(
    founder_id: int,
    session: Session = Depends(get_session),
) -> FounderMatchesOut:
    """Shortlist complementary, available founders for one founder ("find matches").
    Reuses the recombination candidate ranker; deterministic, no LLM."""
    thesis = _active_thesis(session)
    try:
        result = matches_for(session, founder_id, thesis)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FounderMatchesOut(
        founder=MatchFounderOut(**asdict(result.founder)),
        needs=result.needs,
        candidates=[RecombinationCandidateOut(**asdict(c)) for c in result.candidates],
    )


@router.get("/founders/{founder_id}", response_model=FounderDetailOut)
def get_founder(founder_id: int, session: Session = Depends(get_session)) -> Founder:
    founder = session.get(
        Founder,
        founder_id,
        options=[selectinload(Founder.companies), selectinload(Founder.signals)],
    )
    if founder is None:
        raise HTTPException(status_code=404, detail="Founder not found.")
    return founder
