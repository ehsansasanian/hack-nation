"""GET/PUT /thesis - store and retrieve the single active investment thesis.

Thesis-fit filtering and its effect on scoring arrive in Phase 2; this router
is plain configuration storage.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Thesis
from app.schemas import ThesisOut, ThesisUpdate

router = APIRouter(tags=["thesis"])


def _latest(session: Session) -> Thesis | None:
    return session.scalar(select(Thesis).order_by(Thesis.id.desc()))


@router.get("/thesis", response_model=ThesisOut)
def get_thesis(session: Session = Depends(get_session)) -> Thesis:
    thesis = _latest(session)
    if thesis is None:
        raise HTTPException(status_code=404, detail="No thesis configured yet. PUT /thesis to set one.")
    return thesis


@router.put("/thesis", response_model=ThesisOut)
def put_thesis(payload: ThesisUpdate, session: Session = Depends(get_session)) -> Thesis:
    thesis = _latest(session)
    if thesis is None:
        thesis = Thesis(name=payload.name)
        session.add(thesis)
    thesis.name = payload.name
    thesis.sectors = payload.sectors
    thesis.stages = payload.stages
    thesis.geographies = payload.geographies
    thesis.check_size = payload.check_size
    thesis.ownership_target = payload.ownership_target
    thesis.risk_appetite = payload.risk_appetite
    thesis.active = payload.active
    session.commit()
    session.refresh(thesis)
    return thesis
