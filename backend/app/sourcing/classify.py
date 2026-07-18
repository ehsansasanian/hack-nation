"""Map free-text sourcing evidence (topics, titles, descriptions) to a sector.

Sectors are aligned to the thesis vocabulary so a scanned candidate that is
genuinely on-mandate lands in-scope, and one that is not stays honestly
out-of-scope (rather than being force-fit). Returning ``None`` means "no
confident sector" - the thesis filter then excludes it, which is the correct
outcome for an off-mandate find.
"""

from __future__ import annotations

# Checked in priority order; first hit wins. Keywords are substring-matched
# against a lowercased blob of topics + title + description.
_SECTOR_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("health", ("health", "medical", "clinical", "clinic", "patient", "bio", "biotech", "genomic", "care")),
    ("fintech", ("fintech", "payment", "banking", "ledger", "trading", "invoice", "accounting", "defi", "wallet")),
    ("devtools", ("devtools", "developer-tools", "cli", "sdk", "framework", "compiler", "ide", "build-tool", "observability", "ci-cd", "debugger")),
    ("AI infra", ("llm", "inference", "rag", "vector", "embedding", "gpu", "tensor", "ai-agents", "agent", "machine-learning", "ml", "model", "ai", "data", "pipeline")),
)


def classify_sector(*texts: str | None) -> str | None:
    """Return the best-fitting thesis sector for the given text fragments, or None."""
    blob = " ".join(t.lower() for t in texts if t)
    for sector, keywords in _SECTOR_KEYWORDS:
        if any(kw in blob for kw in keywords):
            return sector
    return None
