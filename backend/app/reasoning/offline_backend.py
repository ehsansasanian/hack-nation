"""Deterministic, network-free reasoning backend.

Purpose: keep the whole pipeline runnable with the network off (Phase 7 rehearsal
requirement) and give a reproducible baseline for demos. It reads the *same*
prepared ``ScoringContext`` the LLM sees and scores with transparent heuristics
over the real signal content - so numbers are defensible and data-derived, not
random and not hand-set per company. It is NOT a stand-in for the model's
judgement; provenance is recorded as ``offline-deterministic`` on every score.
"""

from __future__ import annotations

import json

from app.models import Signal
from app.reasoning.backend import ReasoningBackend
from app.reasoning.context import ScoringContext
from app.reasoning.schemas import AxisResult, ColdStartAxisResult, ScreeningResult

_HYPE = ("blockchain", "metaverse", "synergy", "web3", "crypto", "nft", "revolutioniz")
_TRACTION = (
    "design partner", "production", "customer", "mrr", "revenue", "tokens/day",
    "in production", "paying", "users", "acquired", "acquisition",
)
_SHIPPED = ("prototype", "shipped", "shipping", "beta", "early prototype", "tested with", "launched")
_SPECIFIC = ("specific", "first-hand", "named", "validated", "strong domain insight", "wedge")


def _text(sig: Signal) -> str:
    return json.dumps(sig.content, default=str).lower()


def _blob(signals: list[Signal], *extra: str | None) -> str:
    parts = [_text(s) for s in signals]
    parts.extend((e or "").lower() for e in extra)
    return " ".join(parts)


def _max_metric(signals: list[Signal], key: str) -> int:
    best = 0
    for s in signals:
        val = s.content.get(key)
        if isinstance(val, (int, float)):
            best = max(best, int(val))
    return best


def _hits(blob: str, terms: tuple[str, ...]) -> bool:
    return any(t in blob for t in terms)


def _clamp(v: float, lo: float = 1.0, hi: float = 10.0) -> float:
    return round(max(lo, min(hi, v)), 1)


def _ids(signals: list[Signal]) -> list[int]:
    return [s.id for s in signals]


def _trend_from_history(history: list) -> str:
    if not history or len(history) < 2:
        return "stable"
    prev, last = history[-2].get("score"), history[-1].get("score")
    if prev is None or last is None:
        return "stable"
    if last > prev + 0.2:
        return "improving"
    if last < prev - 0.2:
        return "declining"
    return "stable"


class OfflineBackend(ReasoningBackend):
    name = "offline-deterministic"

    def screen(self, ctx: ScoringContext) -> ScreeningResult:
        blob = _blob(
            ctx.company_signals + ctx.founder_signals, ctx.company.one_liner, ctx.deck_text
        )
        hype = sum(1 for t in _HYPE if t in blob) + (1 if "ai " in blob and "blockchain" in blob else 0)
        has_substance = (
            _hits(blob, _TRACTION)
            or _hits(blob, _SHIPPED)
            or _max_metric(ctx.founder_signals, "stars") > 0
            or _max_metric(ctx.founder_signals, "points") > 50
        )
        if hype >= 2 and not has_substance:
            return ScreeningResult(
                viable=False,
                reason="Buzzword-heavy positioning with no shipped product, traction, "
                "or differentiated wedge in any signal.",
            )
        return ScreeningResult(
            viable=True, reason="Has a concrete problem and at least some substantiating signal."
        )

    def score_founder(self, ctx: ScoringContext) -> AxisResult:
        f = ctx.founders[0] if ctx.founders else None
        sigs = ctx.founder_signals
        blob = _blob(sigs, f.bio if f else None)

        score = f.founder_score if (f and f.founder_score is not None) else 4.0
        contributors: list[int] = []

        stars = _max_metric(sigs, "stars")
        if stars:
            score += min(2.0, stars / 5000)
            contributors += [s.id for s in sigs if s.source == "github"]
        points = _max_metric(sigs, "points")
        if points:
            score += min(1.0, points / 400)
            contributors += [s.id for s in sigs if s.source == "hn"]
        if _hits(blob, ("acquired", "acquisition", "exit")):
            score += 1.5
            contributors += [s.id for s in sigs if s.source == "manual"]
        if _hits(blob, _TRACTION):
            score += 1.0
            contributors += [s.id for s in sigs if s.source == "manual"]

        value = _clamp(score, hi=9.8)
        confidence = round(min(0.85, 0.55 + 0.05 * len(sigs)), 2)
        evidence = sorted(set(contributors)) or _ids(sigs)
        trend = _trend_from_history(f.score_history if f else [])
        return AxisResult(
            score=value,
            trend=trend,
            rationale=(
                f"Track-record founder. github_stars={stars or 'n/a'}, hn_points={points or 'n/a'}, "
                f"prior_exit={'yes' if 'acquired' in blob or 'acquisition' in blob else 'no'}, "
                f"traction_signal={'yes' if _hits(blob, _TRACTION) else 'no'}, "
                f"persistent_score_anchor={f.founder_score if f else 'none'}."
            ),
            evidence_signal_ids=evidence,
            confidence=confidence,
        )

    def score_founder_cold_start(self, ctx: ScoringContext) -> ColdStartAxisResult:
        f = ctx.founders[0] if ctx.founders else None
        sigs = ctx.founder_signals
        blob = _blob(sigs, f.bio if f else None, ctx.deck_text, ctx.company.one_liner)

        mid = 3.0
        factors: list[str] = []
        if len(ctx.deck_text) > 200:
            mid += 0.8
            factors.append("deck present")
        if _hits(blob, _SPECIFIC):
            mid += 1.5
            factors.append("specific domain insight")
        if _hits(blob, _SHIPPED):
            mid += 1.3
            factors.append("shipped/prototype (learning velocity)")
        if _problem_founder_fit(blob, ctx.company.sector):
            mid += 1.2
            factors.append("problem-founder fit")
        if sum(1 for t in _HYPE if t in blob) >= 1:
            mid -= 1.0
            factors.append("buzzword penalty")

        mid = _clamp(mid, hi=7.5)
        low = _clamp(mid - 1.5)
        high = _clamp(mid + 1.5, hi=9.0)
        confidence = round(0.30 + 0.03 * len(sigs), 2)  # deliberately low - thin evidence
        return ColdStartAxisResult(
            score_low=low,
            score_high=high,
            rationale=(
                "Cold-start: scored on potential, not track record. Factors: "
                + (", ".join(factors) if factors else "little to assess")
                + f". Range [{low}, {high}] reflects genuine uncertainty."
            ),
            evidence_signal_ids=_ids(sigs),
            confidence=confidence,
        )

    def score_market(self, ctx: ScoringContext) -> AxisResult:
        sigs = ctx.company_signals
        blob = _blob(sigs, ctx.company.one_liner, ctx.deck_text)
        sector = (ctx.company.sector or "").lower()

        score = 5.0
        if sector in ("ai infra", "devtools"):
            score += 1.2
        if _hits(blob, _TRACTION):
            score += 1.6
        if _hits(blob, _SPECIFIC) or _has_numbers(blob):
            score += 1.0
        hype = sum(1 for t in _HYPE if t in blob)
        if hype:
            score -= 1.5 * hype
        if "crowded" in blob or "undifferentiated" in blob:
            score -= 1.5

        value = _clamp(score)
        stance = "bullish" if value >= 7 else "bear" if value <= 4 else "neutral"
        confidence = round(min(0.8, 0.5 + 0.06 * len(sigs)), 2)
        return AxisResult(
            score=value,
            trend="improving" if _hits(blob, _TRACTION) else "stable",
            rationale=(
                f"Market stance: {stance}. sector={sector or 'n/a'}, "
                f"traction={'yes' if _hits(blob, _TRACTION) else 'no'}, "
                f"hype_terms={hype}, crowded={'yes' if 'crowded' in blob else 'no'}."
            ),
            evidence_signal_ids=_ids(sigs),
            confidence=confidence,
        )

    def score_idea(self, ctx: ScoringContext) -> AxisResult:
        sigs = ctx.company_signals
        f = ctx.founders[0] if ctx.founders else None
        blob = _blob(sigs, ctx.company.one_liner, ctx.deck_text)

        score = 5.0
        if _hits(blob, _SPECIFIC) or _has_numbers(blob):
            score += 1.2
        if _hits(blob, _TRACTION):
            score += 1.3
        hype = sum(1 for t in _HYPE if t in blob)
        if hype:
            score -= 1.5 * hype
        if "crowded" in blob or "undifferentiated" in blob:
            score -= 1.0
        # A strong, adaptable team can pivot into the real opportunity.
        pivot_lift = 0.0
        if not ctx.cold_start and f and (f.founder_score or 0) >= 7:
            pivot_lift = 1.0
            score += pivot_lift

        value = _clamp(score)
        confidence = round(min(0.78, 0.5 + 0.05 * len(sigs)), 2)
        return AxisResult(
            score=value,
            trend="stable",
            rationale=(
                "Idea-vs-market: "
                f"specificity={'yes' if _hits(blob, _SPECIFIC) or _has_numbers(blob) else 'no'}, "
                f"traction={'yes' if _hits(blob, _TRACTION) else 'no'}, hype_terms={hype}, "
                f"strong-team pivot lift={pivot_lift}."
            ),
            evidence_signal_ids=_ids(sigs),
            confidence=confidence,
        )


def _has_numbers(blob: str) -> bool:
    return any(ch.isdigit() for ch in blob)


def _problem_founder_fit(blob: str, sector: str | None) -> bool:
    sector = (sector or "").lower()
    pairs = {
        "health": ("midwife", "nurse", "clinic", "trainer", "doctor", "patient", "care"),
        "fintech": ("bank", "trader", "finance", "payments", "accountant"),
        "devtools": ("engineer", "developer", "infra", "ex-deepmind", "built"),
        "ai infra": ("engineer", "ml", "inference", "infra", "researcher"),
    }
    return any(term in blob for term in pairs.get(sector, ()))
