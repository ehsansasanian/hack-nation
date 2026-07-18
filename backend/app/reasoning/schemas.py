"""Structured-output contracts shared by every reasoning backend.

These Pydantic models are what the OpenAI backend requests via strict
``response_format`` and what the deterministic offline backend fills in by hand.
Keeping them in one place means both backends are guaranteed to agree on shape,
and the service layer never has to branch on which backend ran.

Numeric ranges are expressed in the field *descriptions* (which guide the model)
rather than ``ge``/``le`` validators: the latter emit ``minimum``/``maximum`` into
the JSON schema, which strict structured-output mode may reject. The service
clamps values into range instead.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Trend = Literal["improving", "declining", "stable"]


class ScreeningResult(BaseModel):
    """Fast first-pass verdict from the cheap model."""

    viable: bool = Field(description="True if this is worth full 3-axis analysis.")
    reason: str = Field(description="One or two sentences justifying the verdict.")


class AxisResult(BaseModel):
    """One axis of the 3-axis score. Used for founder / market / idea_vs_market."""

    score: float = Field(description="1-10, higher is stronger.")
    trend: Trend
    rationale: str
    evidence_signal_ids: list[int] = Field(
        description="IDs of the provided signals that justify this score."
    )
    confidence: float = Field(description="0-1.")


class ColdStartAxisResult(BaseModel):
    """Founder axis under the cold-start rubric: a score *range*, not a point.

    Low evidence must never collapse to a low point score - it must widen the
    range and lower confidence instead.
    """

    score_low: float = Field(description="Low end of the 1-10 potential range.")
    score_high: float = Field(description="High end of the 1-10 potential range.")
    rationale: str = Field(
        description="Assessment on the potential rubric: deck quality, domain "
        "insight specificity, learning velocity, problem-founder fit."
    )
    evidence_signal_ids: list[int]
    confidence: float = Field(description="0-1, kept low - evidence is thin.")
