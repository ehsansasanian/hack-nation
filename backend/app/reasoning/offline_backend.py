"""Deterministic, network-free reasoning backend.

Purpose: keep the whole pipeline runnable with the network off (Phase 7 rehearsal
requirement) and give a reproducible baseline for demos. It reads the *same*
prepared ``ScoringContext`` the LLM sees and scores with transparent heuristics
over the real signal content - so numbers are defensible and data-derived, not
random and not hand-set per company. It is NOT a stand-in for the model's
judgement; provenance is recorded as ``offline-deterministic`` on every score.

Heuristics are intentionally negation-aware and scoped: track-record and
potential signals are read from *external* signals (github/hn/blog + analyst
notes), never from the founder's own self-reported deck, and unambiguous
positive phrases are used so analyst notes describing an *absence* ("no
customer", "pre-revenue") do not inflate a score.
"""

from __future__ import annotations

import json

from app.models import Signal
from app.reasoning.backend import ReasoningBackend
from app.reasoning.context import ScoringContext
from app.reasoning.schemas import AxisResult, ColdStartAxisResult, ScreeningResult
from app.reasoning.team import assess_team, patterns_tag

_HYPE = ("blockchain", "metaverse", "synergy", "web3", "crypto", "nft", "revolutioniz", "frictionless")
# Unambiguous positives - do not appear inside "no X" / "pre-X" negations.
_POS_TRACTION = (
    "design partner", "in production", "paying", "mrr", "arr", "tokens/day",
    "acquired", "acquisition", "reference call", "customers", "waitlist of",
)
_SHIPPED = ("prototype", "shipped", "shipping", "early prototype", "tested with", "launched beta")
_SPECIFIC = ("specific", "first-hand", "validated", "strong domain insight", "named triggers")
_NEGATIVE = (
    "no product", "no code", "no prototype", "no team", "no specific", "no funding history",
    "buzzword", "undifferentiated", "pre-launch", "pre-revenue", "hopeless",
)


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


def _count(blob: str, terms: tuple[str, ...]) -> int:
    return sum(1 for t in terms if t in blob)


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


def _team_for(ctx: ScoringContext):
    return assess_team(
        ctx.founders,
        {f.id: ctx.signals_for(f.id) for f in ctx.founders},
        ctx.company.sector,
    )


class OfflineBackend(ReasoningBackend):
    name = "offline-deterministic"

    def screen(self, ctx: ScoringContext) -> ScreeningResult:
        signals = ctx.company_signals + ctx.founder_signals
        sig_blob = _blob(signals)  # external evidence only
        hype = _count(_blob(signals, ctx.company.one_liner, ctx.deck_text), _HYPE)
        has_substance = (
            _max_metric(ctx.founder_signals, "stars") > 0
            or _max_metric(ctx.founder_signals, "points") > 50
            or _hits(sig_blob, _POS_TRACTION)
            or any(s.source in ("github", "hn") for s in ctx.founder_signals)
        )
        if hype >= 2 and not has_substance:
            return ScreeningResult(
                viable=False,
                reason=f"Buzzword-heavy positioning ({hype} hype terms) with no shipped "
                "product, metrics, or externally validated traction in any signal.",
            )
        return ScreeningResult(
            viable=True,
            reason="Concrete problem with at least one substantiating external signal.",
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
        prior_exit = _hits(blob, ("acquired", "acquisition", "exit"))
        if prior_exit:
            score += 1.5
            contributors += [s.id for s in sigs if s.source == "manual"]
        traction = _hits(blob, _POS_TRACTION)
        if traction:
            score += 1.0
            contributors += [s.id for s in sigs if s.source == "manual"]

        # Team complementarity is INPUT to the founder axis (never a 4th axis). Solo
        # founders take no penalty (lift stays 0); a multi-founder team is adjusted by
        # its coverage and prior-collaboration signal, and the verdict is named.
        team = _team_for(ctx)
        score += team.lift

        value = _clamp(score, hi=9.8)
        confidence = round(min(0.85, 0.55 + 0.05 * len(sigs)), 2)
        base_evidence = sorted(set(contributors)) or _ids(sigs)
        evidence = sorted(set(base_evidence) | set(team.evidence)) if team.evidence else base_evidence
        rationale = (
            f"Track-record team. github_stars={stars or 'n/a'}, hn_points={points or 'n/a'}, "
            f"prior_exit={'yes' if prior_exit else 'no'}, traction_signal={'yes' if traction else 'no'}, "
            f"persistent_score_anchor={f.founder_score if f else 'none'}. "
            f"Complementarity: {team.verdict} (lift {team.lift:+}). "
            f"{patterns_tag(f, team, prior_exit)}"
        ).strip()
        note = ctx.axis_notes.get("founder")
        if note:
            rationale += f" Mandate emphasis honored: {note}."
        return AxisResult(
            score=value,
            trend=_trend_from_history(f.score_history if f else []),
            rationale=rationale,
            evidence_signal_ids=evidence,
            confidence=confidence,
        )

    def score_founder_cold_start(self, ctx: ScoringContext) -> ColdStartAxisResult:
        f = ctx.founders[0] if ctx.founders else None
        sigs = ctx.founder_signals
        # Potential is read from EXTERNAL signals (no self-reported deck). Venture
        # red flags come from analyst notes + the deck, never the founder bio (a
        # non-technical domain expert must not be penalised for "no code" history).
        external = [s for s in sigs if s.source != "deck"]
        ext_blob = _blob(external)
        fit_blob = _blob(external, f.bio if f else None)
        red_flag_blob = _blob([s for s in sigs if s.source == "manual"], ctx.deck_text)
        negative = _hits(red_flag_blob, _NEGATIVE)
        has_blog = any(s.source == "blog" for s in external)

        mid = 3.0
        factors: list[str] = []
        if len(ctx.deck_text) > 200:
            mid += 0.8
            factors.append("deck present")
        insight = has_blog or (_hits(ext_blob, _SPECIFIC) and not negative)
        if insight:
            mid += 1.5
            factors.append("specific domain insight")
        velocity = _hits(ext_blob, _SHIPPED) and not negative
        if velocity:
            mid += 1.3
            factors.append("shipped/prototype (learning velocity)")
        if _problem_founder_fit(fit_blob, ctx.company.sector):
            mid += 1.2
            factors.append("problem-founder fit")
        if _count(_blob(external, ctx.company.one_liner), _HYPE) >= 1:
            mid -= 1.0
            factors.append("buzzword penalty")
        if negative:
            mid -= 1.0
            factors.append("analyst red flags")

        # Complementarity still matters for a cold-start team (assessed on potential,
        # not track record); a solo cold-start founder takes no extra penalty.
        team = _team_for(ctx)
        if not team.solo:
            mid += team.lift
            factors.append(f"complementarity: {team.verdict} (lift {team.lift:+})")
        elif len(ctx.founders) == 1:
            factors.append("solo founder - flagged risk, no automatic penalty")

        mid = _clamp(mid, hi=7.5)
        low = _clamp(mid - 1.5)
        high = _clamp(mid + 1.5, hi=9.0)
        confidence = round(0.30 + 0.03 * len(sigs), 2)  # deliberately low - thin evidence
        evidence = sorted(set(_ids(sigs)) | set(team.evidence)) if team.evidence else _ids(sigs)
        return ColdStartAxisResult(
            score_low=low,
            score_high=high,
            rationale=(
                "Cold-start: scored on potential, not track record. Factors: "
                + (", ".join(factors) if factors else "little to assess")
                + f". Range [{low}, {high}] reflects genuine uncertainty."
            ),
            evidence_signal_ids=evidence,
            confidence=confidence,
        )

    def score_market(self, ctx: ScoringContext) -> AxisResult:
        sigs = ctx.company_signals
        blob = _blob(sigs, ctx.company.one_liner, ctx.deck_text)
        sig_blob = _blob(sigs)
        sector = (ctx.company.sector or "").lower()

        score = 5.0
        if sector in ("ai infra", "devtools"):
            score += 1.2
        if _hits(sig_blob, _POS_TRACTION):
            score += 1.6
        if _has_numbers(sig_blob) and not _hits(sig_blob, _NEGATIVE):
            score += 0.8
        hype = _count(blob, _HYPE)
        score -= 1.5 * hype
        if _hits(blob, ("crowded", "undifferentiated")):
            score -= 1.5

        value = _clamp(score)
        stance = "bullish" if value >= 7 else "bear" if value <= 4 else "neutral"
        confidence = round(min(0.8, 0.5 + 0.06 * len(sigs)), 2)
        return AxisResult(
            score=value,
            trend="improving" if _hits(sig_blob, _POS_TRACTION) else "stable",
            rationale=(
                f"Market stance: {stance}. sector={sector or 'n/a'}, "
                f"traction={'yes' if _hits(sig_blob, _POS_TRACTION) else 'no'}, "
                f"hype_terms={hype}, crowded={'yes' if _hits(blob, ('crowded', 'undifferentiated')) else 'no'}."
            ),
            evidence_signal_ids=_ids(sigs),
            confidence=confidence,
        )

    def score_idea(self, ctx: ScoringContext) -> AxisResult:
        sigs = ctx.company_signals
        f = ctx.founders[0] if ctx.founders else None
        blob = _blob(sigs, ctx.company.one_liner, ctx.deck_text)
        sig_blob = _blob(sigs)

        score = 5.0
        if _hits(sig_blob, _SPECIFIC) and not _hits(sig_blob, _NEGATIVE):
            score += 1.2
        if _hits(sig_blob, _POS_TRACTION):
            score += 1.3
        hype = _count(blob, _HYPE)
        score -= 1.5 * hype
        if _hits(blob, ("crowded", "undifferentiated")):
            score -= 1.0
        # A strong, adaptable team can pivot into the real opportunity.
        pivot_lift = 1.0 if (not ctx.cold_start and f and (f.founder_score or 0) >= 7) else 0.0
        score += pivot_lift

        value = _clamp(score)
        confidence = round(min(0.78, 0.5 + 0.05 * len(sigs)), 2)
        return AxisResult(
            score=value,
            trend="stable",
            rationale=(
                "Idea-vs-market: "
                f"specificity={'yes' if _hits(sig_blob, _SPECIFIC) else 'no'}, "
                f"traction={'yes' if _hits(sig_blob, _POS_TRACTION) else 'no'}, hype_terms={hype}, "
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
