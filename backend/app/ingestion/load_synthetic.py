"""Load the committed synthetic dataset through the shared ingestion pipeline.

Run: ``uv run python -m app.ingestion.load_synthetic``

Every profile is pushed through ``ingest_signal`` - the exact path live scrapers
use - so dedup and entity resolution are exercised identically. The dataset is
deterministic and committed; nothing is generated at runtime.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DECKS_DIR, SYNTHETIC_DIR
from app.db import SessionLocal, init_db
from app.ingestion.deck_parser import extract_text
from app.ingestion.pipeline import CompanyHint, FounderHint, RawSignal, ingest_signal
from app.models import Application, Company, Founder, Signal


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _founder_hint(profile: dict) -> FounderHint | None:
    f = profile.get("founder")
    if not f:
        return None
    return FounderHint(
        name=f.get("name"),
        github_handle=f.get("github_handle"),
        links=f.get("links", {}),
        bio=f.get("bio"),
        founder_score=f.get("founder_score"),
        score_history=f.get("score_history", []),
    )


def _company_hint(profile: dict) -> CompanyHint | None:
    c = profile.get("company")
    if not c:
        return None
    return CompanyHint(
        name=c.get("name"),
        domain=c.get("domain"),
        sector=c.get("sector"),
        stage=c.get("stage"),
        geography=c.get("geography"),
        one_liner=c.get("one_liner"),
    )


def _get_or_create_application(session: Session, company_id: int, deck_text: str) -> None:
    existing = session.scalar(
        select(Application).where(
            Application.company_id == company_id, Application.origin == "inbound"
        )
    )
    if existing is None:
        session.add(
            Application(
                company_id=company_id,
                deck_text=deck_text,
                origin="inbound",
                status="in_review",
            )
        )
    else:
        existing.deck_text = deck_text


def _load_profile(session: Session, profile: dict) -> None:
    fhint = _founder_hint(profile)
    chint = _company_hint(profile)
    company_id: int | None = None

    for sig in profile.get("signals", []):
        signal, _ = ingest_signal(
            session,
            RawSignal(
                source=sig["source"],
                content=sig.get("content", {}),
                timestamp=_parse_ts(sig["timestamp"]),
                dedup_key=sig.get("dedup_key"),
                founder=fhint,
                company=chint,
            ),
        )
        company_id = company_id or signal.company_id

    deck = profile.get("deck")
    if deck:
        deck_text = extract_text(DECKS_DIR / deck)
        signal, _ = ingest_signal(
            session,
            RawSignal(
                source="deck",
                content={"kind": "pitch_deck", "file": deck, "excerpt": deck_text[:280]},
                timestamp=_parse_ts(profile.get("applied_at", profile["signals"][0]["timestamp"])),
                dedup_key=f"deck:{deck}",
                founder=fhint,
                company=chint,
            ),
        )
        company_id = company_id or signal.company_id
        if company_id is not None:
            _get_or_create_application(session, company_id, deck_text)


def _summary(session: Session) -> dict[str, int]:
    return {
        "founders": session.scalar(select(func.count()).select_from(Founder)) or 0,
        "companies": session.scalar(select(func.count()).select_from(Company)) or 0,
        "signals": session.scalar(select(func.count()).select_from(Signal)) or 0,
        "applications": session.scalar(select(func.count()).select_from(Application)) or 0,
    }


def main() -> None:
    init_db()
    files = sorted(SYNTHETIC_DIR.glob("*.json"))
    session = SessionLocal()
    try:
        for path in files:
            _load_profile(session, json.loads(Path(path).read_text()))
        session.commit()
        counts = _summary(session)
    finally:
        session.close()

    print(f"Loaded {len(files)} synthetic profiles.")
    for key, value in counts.items():
        print(f"  {key:13} {value}")


if __name__ == "__main__":
    main()
