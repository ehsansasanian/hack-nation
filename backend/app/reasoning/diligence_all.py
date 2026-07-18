"""Run diligence + memo across every scored application.

Run: ``uv run python -m app.reasoning.diligence_all [--backend offline|openai]``
     ``uv run python -m app.reasoning.diligence_all --no-memo``

Mirrors ``reasoning.score_all``: it operates on applications that already carry
axis scores (Phase 2), runs the diligence pipeline (claim extraction -> truth-gap
-> validator) and then the memo generator on each, and prints a compact table.
With the OpenAI backend it also prints the token/cost estimate.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Application, Score
from app.reasoning.diligence import run_diligence
from app.reasoning.memo import generate_memo
from app.reasoning.score_all import ensure_thesis


def _scored_application_ids(session: Session) -> list[int]:
    return list(
        session.scalars(
            select(Application.id)
            .join(Score, Score.application_id == Application.id)
            .distinct()
            .order_by(Application.id)
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["offline", "openai"], default=None)
    parser.add_argument("--no-memo", action="store_true", help="run diligence only")
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        ensure_thesis(session)
        app_ids = _scored_application_ids(session)
        print(
            f"\nDiligence{'' if args.no_memo else ' + memo'} on {len(app_ids)} scored "
            f"applications (backend={args.backend or 'auto'})\n"
        )
        header = f"{'id':>3}  {'company':22}  {'claims':>6}  {'contra':>6}  {'verif':>5}  {'unsupported axes':20}  recommendation"
        print(header)
        print("-" * len(header))
        for app_id in app_ids:
            outcome = run_diligence(session, app_id, prefer_backend=args.backend)
            company = session.get(Application, app_id).company.name
            rec = "-"
            if not args.no_memo:
                memo = generate_memo(session, app_id, prefer_backend=args.backend)
                rec = memo.recommendation.split(" - ")[0]
            print(
                f"{app_id:>3}  {company[:22]:22}  {len(outcome.claims):>6}  "
                f"{outcome.n_contradicted:>6}  {outcome.n_verified:>5}  "
                f"{(', '.join(outcome.unsupported_axes) or '-')[:20]:20}  {rec}"
            )
    finally:
        session.close()

    from app.reasoning.openai_backend import USAGE

    if USAGE.by_model:
        print("\nOpenAI usage:", USAGE.report())


if __name__ == "__main__":
    main()
