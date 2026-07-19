"""Database engine, session factory, and schema bootstrap."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Columns added after the first schema was created. On SQLite ``create_all`` will
# not alter an existing table, so we add missing columns idempotently on startup.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    # Auto-analysis pipeline stage + last error, added after the first schema.
    "applications": {
        "outreach_draft": "TEXT",
        "analysis_status": "TEXT",
        "analysis_error": "TEXT",
        # Inbound enrichment (Phase 8): self-declared links + per-source fetch report.
        "declared_links": "JSON",
        "enrichment_report": "JSON",
    },
    # Phase 4 traceability columns (signal -> claim -> trust -> memo chain).
    "claims": {"source": "TEXT", "validator_note": "TEXT"},
    "scores": {"validator_note": "TEXT"},
}


def _apply_additive_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue  # fresh DB: create_all already built the full table
            present = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


# Backfill for rows created before ``analysis_status`` existed. Idempotent: only
# touches rows where the column is still NULL, so it is safe to run on every
# startup and after a demo re-seed. Precedence mirrors how far the pipeline got:
# a memo means the whole chain finished (ready); an explicitly screened-out app is
# terminal; scores-without-a-memo is a partial run left at the scoring stage; a
# bare application has not been analysed yet (received).
_BACKFILL_ANALYSIS_STATUS = """
UPDATE applications
SET analysis_status = CASE
    WHEN id IN (SELECT application_id FROM memos)  THEN 'ready'
    WHEN status = 'screened_out'                   THEN 'screened_out'
    WHEN id IN (SELECT application_id FROM scores) THEN 'scoring'
    ELSE 'received'
END
WHERE analysis_status IS NULL
"""


def backfill_analysis_status() -> None:
    """Give every application a sensible ``analysis_status`` if it lacks one."""
    inspector = inspect(engine)
    if "applications" not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns("applications")}
    if "analysis_status" not in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(_BACKFILL_ANALYSIS_STATUS))


def init_db() -> None:
    """Create all tables, apply additive migrations, backfill. Safe to call repeatedly."""
    from app.models import Base  # imported here so all models register on Base

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()
    backfill_analysis_status()
