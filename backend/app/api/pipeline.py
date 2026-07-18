"""GET /pipeline - ranked (for now, recency-ordered) list of applications."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Application
from app.schemas import ApplicationOut

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline", response_model=list[ApplicationOut])
def get_pipeline(
    status: str | None = None,
    origin: str | None = None,
    session: Session = Depends(get_session),
) -> list[Application]:
    stmt = (
        select(Application)
        .options(selectinload(Application.company), selectinload(Application.scores))
        .order_by(Application.created_at.desc())
    )
    if status:
        stmt = stmt.where(Application.status == status)
    if origin:
        stmt = stmt.where(Application.origin == origin)
    return list(session.scalars(stmt).all())
