"""Map free-text sourcing evidence (topics, titles, descriptions) to a sector.

Sectors are aligned to the thesis vocabulary so a scanned candidate that is
genuinely on-mandate lands in-scope, and one that is not stays honestly
out-of-scope (rather than being force-fit). Returning ``None`` means "no
confident sector" - the thesis filter then excludes it, which is the correct
outcome for an off-mandate find.
"""

from __future__ import annotations

import re

# Checked in priority order; first hit wins. Keywords are matched on word
# boundaries against a lowercased blob of topics + title + description, so short
# tokens like "ai"/"ml" don't spuriously fire inside words ("airline", "laid").
_SECTOR_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("health", ("health", "medical", "clinical", "clinic", "patient", "biotech", "genomic", "healthcare")),
    ("fintech", ("fintech", "payment", "payments", "banking", "ledger", "trading", "invoice", "accounting", "defi", "wallet")),
    ("devtools", ("devtools", "developer-tools", "cli", "sdk", "framework", "compiler", "ide", "observability", "ci-cd", "debugger", "devtool")),
    ("AI infra", ("llm", "inference", "rag", "vector", "embedding", "gpu", "tensor", "ai-agents", "agent", "agents", "machine-learning", "ml", "model", "ai", "rag", "mlops")),
)
_COMPILED = tuple(
    (sector, re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b"))
    for sector, kws in _SECTOR_KEYWORDS
)


def classify_sector(*texts: str | None) -> str | None:
    """Return the best-fitting thesis sector for the given text fragments, or None."""
    blob = " ".join(t.lower() for t in texts if t)
    for sector, pattern in _COMPILED:
        if pattern.search(blob):
            return sector
    return None
