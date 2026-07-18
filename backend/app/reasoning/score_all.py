"""Score every application through the Phase 2 pipeline.

Run: ``uv run python -m app.reasoning.score_all [--force] [--backend offline|openai]``

Ensures a default thesis exists (idempotent), then runs
``score_application`` over every application and prints a compact result table.
With the OpenAI backend it also prints the token/cost estimate.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Application, Thesis
from app.reasoning.analysis import stamp_analysis_status
from app.reasoning.service import ScoringOutcome, score_application

_DEFAULT_THESIS = dict(
    name="Pre-seed technical founders, AI-native",
    sectors=["AI infra", "devtools", "fintech", "health"],
    stages=["pre-seed", "seed"],
    geographies=[],  # empty = no geographic constraint
    check_size="$100K",
    ownership_target="7-10%",
    risk_appetite="high",
    active=True,
)


def ensure_thesis(session: Session) -> Thesis:
    thesis = session.scalar(select(Thesis).order_by(Thesis.id.desc()))
    if thesis is None:
        thesis = Thesis(**_DEFAULT_THESIS)
        session.add(thesis)
        session.commit()
        print(f"Seeded default thesis: {thesis.name}")
    return thesis


def _fmt_axis(outcome: ScoringOutcome, axis: str) -> str:
    for s in outcome.scores:
        if s.axis == axis:
            if s.cold_start and s.score_low is not None:
                return f"{s.value}[{s.score_low}-{s.score_high}]c{s.confidence}"
            return f"{s.value}(c{s.confidence})"
    return "-"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="score even if screened out")
    parser.add_argument("--backend", choices=["offline", "openai"], default=None)
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        ensure_thesis(session)
        apps = list(session.scalars(select(Application).order_by(Application.id)).all())
        print(f"\nScoring {len(apps)} applications (backend={args.backend or 'auto'}, force={args.force})\n")
        header = f"{'id':>3}  {'company':22}  {'status':12}  {'screen':10}  {'cold':4}  {'founder':16}  {'market':12}  {'idea':12}  backend"
        print(header)
        print("-" * len(header))
        for app in apps:
            outcome = score_application(
                session, app.id, force=args.force, prefer_backend=args.backend
            )
            company = session.get(Application, app.id).company.name
            print(
                f"{app.id:>3}  {company[:22]:22}  {outcome.status:12}  "
                f"{(outcome.screening_verdict or '-'):10}  {str(outcome.cold_start):4}  "
                f"{_fmt_axis(outcome, 'founder'):16}  {_fmt_axis(outcome, 'market'):12}  "
                f"{_fmt_axis(outcome, 'idea_vs_market'):12}  {outcome.backend}"
            )
        # Keep analysis_status in step with the batch scoring pass.
        stamp_analysis_status(session)
    finally:
        session.close()

    from app.reasoning.openai_backend import USAGE

    if USAGE.by_model:
        print("\nOpenAI usage:", USAGE.report())


if __name__ == "__main__":
    main()
