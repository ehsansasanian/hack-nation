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
    "applications": {"outreach_draft": "TEXT"},
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


def init_db() -> None:
    """Create all tables, then apply additive column migrations. Safe to call repeatedly."""
    from app.models import Base  # imported here so all models register on Base

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations()
