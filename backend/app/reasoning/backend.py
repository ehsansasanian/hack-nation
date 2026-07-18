"""Reasoning backend seam.

Two interchangeable implementations satisfy one interface:

* ``OpenAIBackend`` - real structured-output calls (gpt-4o-mini to screen, gpt-4o
  per axis). This is the product path.
* ``OfflineBackend`` - a deterministic heuristic over the same prepared context,
  so the pipeline runs (and the demo works) with the network off, per the
  Phase 7 "rehearse offline" requirement.

Selection is env-driven (``VC_BRAIN_LLM``: ``openai`` | ``offline`` | ``auto``).
The service layer may additionally fall back to offline if a live call fails.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from app.config import OPENAI_API_KEY
from app.reasoning.context import ScoringContext
from app.reasoning.schemas import AxisResult, ColdStartAxisResult, ScreeningResult


class ReasoningBackend(ABC):
    name: str

    @abstractmethod
    def screen(self, ctx: ScoringContext) -> ScreeningResult: ...

    @abstractmethod
    def score_founder(self, ctx: ScoringContext) -> AxisResult: ...

    @abstractmethod
    def score_founder_cold_start(self, ctx: ScoringContext) -> ColdStartAxisResult: ...

    @abstractmethod
    def score_market(self, ctx: ScoringContext) -> AxisResult: ...

    @abstractmethod
    def score_idea(self, ctx: ScoringContext) -> AxisResult: ...


def get_backend(prefer: str | None = None) -> ReasoningBackend:
    """Return the configured backend.

    ``prefer`` (or ``VC_BRAIN_LLM``): ``openai`` forces the live path, ``offline``
    forces the deterministic path, ``auto`` (default) uses OpenAI when a key is
    present and offline otherwise.
    """
    mode = (prefer or os.getenv("VC_BRAIN_LLM", "auto")).strip().lower()

    # Imported lazily so the offline path has zero import-time dependency on openai.
    if mode == "offline":
        from app.reasoning.offline_backend import OfflineBackend

        return OfflineBackend()
    if mode == "openai" or (mode == "auto" and OPENAI_API_KEY):
        from app.reasoning.openai_backend import OpenAIBackend

        return OpenAIBackend()
    from app.reasoning.offline_backend import OfflineBackend

    return OfflineBackend()
