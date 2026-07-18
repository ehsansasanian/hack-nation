"""GET /founders/{id} - founder profile with persistent score history and signals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Founder
from app.schemas import FounderDetailOut

router = APIRouter(tags=["founders"])


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
