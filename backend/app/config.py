"""Runtime configuration, sourced from environment variables.

A minimal ``.env`` loader is included so local runs pick up ``backend/.env``
without an extra dependency. The runtime environment always wins over the file.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
DECKS_DIR = DATA_DIR / "decks"


def _load_env_file(path: Path) -> None:
    """Populate ``os.environ`` from a KEY=VALUE file.

    A non-empty value in ``backend/.env`` wins over any pre-existing environment
    variable, so a stale key exported in the shell can never shadow the project's
    own configuration. Keys the file leaves blank fall through to the environment.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        value = raw.strip().strip('"').strip("'")
        if value:
            os.environ[key] = value  # file is authoritative when it specifies a value
        else:
            os.environ.setdefault(key, value)


_load_env_file(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "vc_brain.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
