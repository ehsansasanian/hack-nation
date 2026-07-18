"""Rebuild the canonical demo database from scratch, deterministically.

Run: ``uv run python -m app.demo_seed``

One command that reproduces the exact baseline demo state with the network off:

    drop everything -> load the committed synthetic profiles -> 3-axis scoring
    (offline) -> diligence + memo (offline)

The offline deterministic backend is pinned throughout, so this **never** calls a
live LLM, and it **never** runs the live outbound scanners - the baseline state is
fully reproducible and stable across machines. (Live GitHub/HN sourcing is the one
on-stage moment that needs the network; those outbound rows are intentionally not
part of the reproducible baseline.)

Starting from a dropped schema also guarantees no leftover rows from earlier ad-hoc
runs survive into the demo.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SYNTHETIC_DIR
from app.db import SessionLocal, engine, init_db
from app.ingestion.load_synthetic import _load_profile, _summary
from app.models import Application, Base, Claim, Memo, Score
from app.reasoning.analysis import stamp_analysis_status
from app.reasoning.diligence import run_diligence
from app.reasoning.memo import generate_memo
from app.reasoning.score_all import ensure_thesis
from app.reasoning.service import score_application

BACKEND = "offline"  # pinned: deterministic, no network, ever.


def _reset_schema() -> None:
    """Drop every table then recreate - a guaranteed-clean starting point."""
    Base.metadata.drop_all(bind=engine)
    init_db()


def _load_synthetic(session: Session) -> dict[str, int]:
    for path in sorted(SYNTHETIC_DIR.glob("*.json")):
        _load_profile(session, json.loads(Path(path).read_text()))
    session.commit()
    return _summary(session)


def _count(session: Session, model) -> int:
    return len(list(session.scalars(select(model))))


def main() -> None:
    print("Rebuilding the canonical demo DB (offline, deterministic)\n")

    _reset_schema()
    session = SessionLocal()
    try:
        counts = _load_synthetic(session)
        print(
            f"1. Ingested synthetic dataset: {counts['signals']} signals, "
            f"{counts['founders']} founders, {counts['companies']} companies, "
            f"{counts['applications']} inbound applications."
        )

        ensure_thesis(session)
        app_ids = list(session.scalars(select(Application.id).order_by(Application.id)))

        scored: list[int] = []
        cold_start = 0
        for app_id in app_ids:
            outcome = score_application(session, app_id, prefer_backend=BACKEND)
            if outcome.scores:
                scored.append(app_id)
            if outcome.cold_start:
                cold_start += 1
        screened_out = len(app_ids) - len(scored)
        print(
            f"2. Scored {len(scored)} applications on 3 independent axes "
            f"({screened_out} screened out at first pass, {cold_start} cold-start)."
        )

        contradicted = 0
        memos = 0
        for app_id in scored:
            outcome = run_diligence(session, app_id, prefer_backend=BACKEND)
            if outcome.n_contradicted:
                contradicted += 1
            generate_memo(session, app_id, prefer_backend=BACKEND)
            memos += 1
        print(
            f"3. Diligence + memo on {memos} scored applications "
            f"({contradicted} with a contradicted claim surfaced)."
        )

        # Stamp each application's auto-analysis stage from how far the chain got
        # (memo -> ready, screened_out -> screened_out) so the seeded DB reflects the
        # completed pipeline rather than the default 'received'.
        stamp_analysis_status(session)

        print(
            "\nDemo DB ready: "
            f"{_count(session, Application)} applications, "
            f"{_count(session, Score)} scores, "
            f"{_count(session, Claim)} claims, "
            f"{_count(session, Memo)} memos."
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
