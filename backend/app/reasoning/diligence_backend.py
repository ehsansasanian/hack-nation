"""Diligence backend seam (Phase 4), mirroring ``reasoning/backend.py``.

Two interchangeable implementations satisfy one interface:

* ``OpenAIDiligenceBackend`` - real structured-output calls (the product path).
* ``OfflineDiligenceBackend`` - deterministic heuristics over the same prepared
  ``DiligenceContext``, so diligence + memo + query all run with the network off.

Selection is env-driven (same ``VC_BRAIN_LLM`` switch the scoring seam uses), and
the orchestrator additionally falls back to offline if a live call fails.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from app.config import OPENAI_API_KEY
from app.reasoning.diligence_context import DiligenceContext
from app.reasoning.diligence_schemas import (
    ClaimAssessment,
    ExtractedClaim,
    MemoSections,
    ParsedQuery,
    ValidatorReport,
)


class DiligenceBackend(ABC):
    """One interface, two implementations. Methods land in Phase 4 unit order:
    claim extraction -> truth-gap (assess) -> validator -> memo -> NL query."""

    name: str

    @abstractmethod
    def extract_claims(self, ctx: DiligenceContext) -> list[ExtractedClaim]: ...

    @abstractmethod
    def assess_claims(
        self, ctx: DiligenceContext, claims: list[ExtractedClaim]
    ) -> list[ClaimAssessment]: ...

    @abstractmethod
    def validate(
        self, ctx: DiligenceContext, assessments: list[ClaimAssessment]
    ) -> ValidatorReport: ...

    @abstractmethod
    def write_memo(
        self, ctx: DiligenceContext, assessments: list[ClaimAssessment]
    ) -> MemoSections: ...

    @abstractmethod
    def parse_query(self, query: str) -> ParsedQuery: ...


def get_diligence_backend(prefer: str | None = None) -> DiligenceBackend:
    """Return the configured diligence backend (see ``reasoning.backend.get_backend``)."""
    mode = (prefer or os.getenv("VC_BRAIN_LLM", "auto")).strip().lower()

    if mode == "offline":
        from app.reasoning.diligence_offline import OfflineDiligenceBackend

        return OfflineDiligenceBackend()
    if mode == "openai" or (mode == "auto" and OPENAI_API_KEY):
        from app.reasoning.diligence_openai import OpenAIDiligenceBackend

        return OpenAIDiligenceBackend()
    from app.reasoning.diligence_offline import OfflineDiligenceBackend

    return OfflineDiligenceBackend()
