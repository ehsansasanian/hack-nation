"""Deck text extraction. Claim structuring is a later phase - this only reads.

PDFs go through PyMuPDF; plain-text decks are read directly.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def extract_text(path: str | Path) -> str:
    """Return the raw text of a deck (.pdf via PyMuPDF, otherwise read as text)."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return _extract_pdf(path)
    return path.read_text(encoding="utf-8").strip()


def _extract_pdf(path: Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc).strip()
