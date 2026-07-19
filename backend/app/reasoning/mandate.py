"""Customizable fund guidelines + investor-vocabulary mandate constraints (Phase 8).

Two jobs, both deterministic and backend-agnostic:

1. **Guidance injection.** ``render_guidance`` turns a ``Thesis``'s free-text
   investment principles, per-axis emphasis notes and curated constraints into a
   compact block that is threaded into the screening AND axis-scoring prompts (and
   surfaced as its own step in the reasoning trace). ``axis_note`` pulls the
   per-axis emphasis note. ``FOUNDER_SUCCESS_RUBRIC`` is the research-backed
   founder-success rubric folded into the founder axis - it is a constant, NEVER
   configurable, and is cited in the rationale by both backends.

2. **Mandate-vs-realized fit.** ``evaluate_mandate_fit`` compares each *configured*
   constraint against the realized/claimed value read from the company, the deck,
   the diligence claims and the stored signals, tagging each ``met`` / ``gap`` /
   ``unknown``. This is the visible payoff of the shared vocabulary and is rendered
   as the memo's "Mandate fit" block. Realized values are only ever read from
   evidence we actually hold - a value we cannot find is ``unknown``, never invented.

NEVER configurable (guarded by omission - there is no knob for these): axis
weights, axis averaging, trust levels, diligence honesty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import Claim, Company, Founder, Score, Signal, Thesis

# Folded into the founder axis rubric (both backends cite it). Constant, not a knob.
FOUNDER_SUCCESS_RUBRIC = (
    "Research-backed founder-success patterns to weigh (evidence, not a formula): "
    "(1) serial-founder premium - a prior founded company, especially one with an "
    "exit, predicts higher odds; (2) technical-CEO / technical-founder effect - a "
    "technical founder on a technical product correlates with execution; (3) team "
    "complementarity - covered technical AND commercial bases with low overlap and "
    "prior collaboration beat solo or single-skill teams. Treat a solo founder as a "
    "flagged risk with rationale, never an automatic penalty."
)

_TECHNICAL_KW = (
    "engineer", "engineering", "cto", " ml", "machine learning", "phd", "infra",
    "infrastructure", "developer", "backend", "systems", "researcher", "research",
    "built", "shipped", "compiler", "kernel", "ex-deepmind", "ex-google", "hacker",
)
_COMMERCIAL_KW = (
    "ceo", "sales", "gtm", "go-to-market", "business", "commercial", "growth",
    "marketing", "operations", "bd", "revenue", "partnerships", "founder & ceo",
    "product manager", "finance", "operator",
)


# --- guidance injection ------------------------------------------------------


def _constraints_lines(thesis: Thesis) -> list[str]:
    """One line per configured curated constraint - the vocabulary the prompt sees."""
    lines: list[str] = []
    if thesis.business_model:
        lines.append(f"business model target: {thesis.business_model}")
    if thesis.min_arr_usd:
        lines.append(f"minimum ARR traction gate: ${_human_usd(thesis.min_arr_usd)}")
    if thesis.min_growth_rate:
        lines.append(f"minimum growth rate: {thesis.min_growth_rate}")
    if thesis.require_technical_founder:
        lines.append("requires a technical founder on the team")
    if thesis.valuation_cap:
        lines.append(f"entry valuation ceiling: {thesis.valuation_cap}")
    if thesis.instrument:
        lines.append(f"preferred instrument: {thesis.instrument}")
    if thesis.exclusions:
        lines.append(f"exclusions (no-invest): {', '.join(thesis.exclusions)}")
    return lines


def render_guidance(thesis: Thesis | None) -> str:
    """The fund-guidance block injected into every screening/axis prompt.

    Empty string when nothing is configured, so an un-customized mandate injects
    nothing. Kept compact - it rides on top of the hard-filter thesis rationale.
    """
    if thesis is None:
        return ""
    parts: list[str] = []
    principles = (thesis.investment_principles or "").strip()
    if principles:
        parts.append(f"INVESTMENT PRINCIPLES (weigh these): {principles}")
    constraints = _constraints_lines(thesis)
    if constraints:
        parts.append("MANDATE CONSTRAINTS: " + "; ".join(constraints) + ".")
    return "\n".join(parts)


def axis_note(thesis: Thesis | None, axis: str) -> str:
    """Per-axis emphasis note the mandate configured for one axis, or ''."""
    if thesis is None:
        return ""
    notes = thesis.axis_notes or {}
    return str(notes.get(axis, "") or "").strip()


# --- realized-value extraction (evidence only; never invents) ----------------

_NUM_RE = re.compile(r"\$?\s?\d[\d,]*\.?\d*\s?(?:k|m|b|bn|million|billion|thousand)?", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d[\d,]*\.?\d*)\s?%")
_PRE_REVENUE = ("pre-revenue", "prerevenue", "no revenue", "$0", "not yet monetiz", "not monetiz", "zero revenue")


def _to_usd(token: str) -> float | None:
    t = token.strip().lower().replace("$", "").replace(",", "").replace(" ", "")
    mult = 1.0
    for suffix, factor in (("billion", 1e9), ("bn", 1e9), ("million", 1e6), ("thousand", 1e3), ("b", 1e9), ("m", 1e6), ("k", 1e3)):
        if t.endswith(suffix):
            mult, t = factor, t[: -len(suffix)]
            break
    try:
        return float(t) * mult
    except ValueError:
        return None


def _human_usd(v: float) -> str:
    if v >= 1e9:
        return f"{v / 1e9:g}B"
    if v >= 1e6:
        return f"{v / 1e6:g}M"
    if v >= 1e3:
        return f"{v / 1e3:g}K"
    return f"{v:g}"


def _find_revenue_usd(blob: str) -> float | None:
    """Largest ARR/MRR figure stated in the text (MRR annualized), or 0 if pre-revenue."""
    low = blob.lower()
    best: float | None = None
    for m in re.finditer(r"(\$?\s?\d[\d,]*\.?\d*\s?(?:k|m|b|bn|million|billion|thousand)?)\s*(arr|mrr|/month|per month|/mo|revenue)", low):
        val = _to_usd(m.group(1))
        if val is None:
            continue
        if m.group(2) in ("mrr", "/month", "per month", "/mo"):
            val *= 12
        best = val if best is None else max(best, val)
    if best is None and any(t in low for t in _PRE_REVENUE):
        return 0.0
    return best


def _find_growth_pct(blob: str) -> float | None:
    m = re.search(r"(\d[\d,]*\.?\d*)\s?%\s*(mom|wow|yoy|month|week|growth|growing)", blob.lower())
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _find_valuation_usd(blob: str) -> float | None:
    m = re.search(r"(?:valuation|post-money|pre-money|cap of|at a? cap|raising at)\D{0,12}(\$?\s?\d[\d,]*\.?\d*\s?(?:k|m|b|bn|million|billion)?)", blob.lower())
    return _to_usd(m.group(1)) if m else None


def _team_is_technical(founders: list[Founder], signals: list[Signal]) -> bool:
    if any(f.github_handle for f in founders):
        return True
    if any(s.source == "github" for s in signals):
        return True
    for f in founders:
        if any(kw in (f.bio or "").lower() for kw in _TECHNICAL_KW):
            return True
    return False


# --- mandate fit -------------------------------------------------------------


@dataclass(slots=True)
class MandateConstraint:
    label: str
    target: str
    realized: str
    status: str  # met | gap | unknown


def _in_list(value: str | None, allowed: list[str]) -> bool:
    v = (value or "").strip().lower()
    return v in {a.strip().lower() for a in allowed}


def evaluate_mandate_fit(
    thesis: Thesis | None,
    company: Company,
    founders: list[Founder],
    claims: list[Claim],
    scores: list[Score],
    deck_text: str,
    signals: list[Signal],
) -> list[MandateConstraint]:
    """Each configured constraint vs its realized/claimed value (met/gap/unknown).

    Only *configured* constraints are emitted, so the block stays tight. Realized
    values are read from company facts + deck + claims + signals; anything we cannot
    find is ``unknown`` (never fabricated).
    """
    if thesis is None:
        return []
    out: list[MandateConstraint] = []
    claim_blob = " ".join(c.text for c in claims)
    blob = " ".join([deck_text or "", company.one_liner or "", claim_blob])

    # Hard filters (shown for transparency; the actual gate lives in thesis_fit).
    if thesis.sectors:
        hit = _in_list(company.sector, thesis.sectors)
        out.append(MandateConstraint("Sector", ", ".join(thesis.sectors), company.sector or "unknown", "met" if hit else "gap"))
    if thesis.stages:
        hit = _in_list(company.stage, thesis.stages)
        out.append(MandateConstraint("Stage", ", ".join(thesis.stages), company.stage or "unknown", "met" if hit else "gap"))
    if thesis.geographies:
        hit = _in_list(company.geography, thesis.geographies)
        out.append(MandateConstraint("Geography", ", ".join(thesis.geographies), company.geography or "unknown", "met" if hit else "gap"))
    if thesis.exclusions:
        excluded = _in_list(company.sector, thesis.exclusions) or any(
            e.strip().lower() in blob.lower() for e in thesis.exclusions if e.strip()
        )
        out.append(MandateConstraint(
            "Exclusions", "no-invest: " + ", ".join(thesis.exclusions),
            "matches an exclusion" if excluded else "clear",
            "gap" if excluded else "met",
        ))

    # Traction gate: ARR floor.
    if thesis.min_arr_usd:
        realized = _find_revenue_usd(blob)
        target = f"${_human_usd(thesis.min_arr_usd)} ARR"
        if realized is None:
            out.append(MandateConstraint("ARR floor", target, "not disclosed", "unknown"))
        elif realized >= thesis.min_arr_usd:
            out.append(MandateConstraint("ARR floor", target, f"${_human_usd(realized)} ARR", "met"))
        else:
            shown = "pre-revenue" if realized == 0 else f"${_human_usd(realized)} ARR"
            out.append(MandateConstraint("ARR floor", target, shown, "gap"))

    # Growth-rate floor.
    if thesis.min_growth_rate:
        realized = _find_growth_pct(blob)
        floor = _find_growth_pct(thesis.min_growth_rate)
        if realized is None:
            out.append(MandateConstraint("Growth floor", thesis.min_growth_rate, "not disclosed", "unknown"))
        elif floor is None or realized >= floor:
            out.append(MandateConstraint("Growth floor", thesis.min_growth_rate, f"{realized:g}%", "met"))
        else:
            out.append(MandateConstraint("Growth floor", thesis.min_growth_rate, f"{realized:g}%", "gap"))

    # Technical-founder requirement.
    if thesis.require_technical_founder:
        tech = _team_is_technical(founders, signals)
        out.append(MandateConstraint(
            "Technical founder", "required",
            "present" if tech else "none detected", "met" if tech else "gap",
        ))

    # Business-model type.
    if thesis.business_model:
        toks = [t for t in re.split(r"[^a-z0-9]+", thesis.business_model.lower()) if len(t) >= 2]
        hit = any(t in blob.lower() for t in toks)
        out.append(MandateConstraint(
            "Business model", thesis.business_model,
            thesis.business_model if hit else "not stated", "met" if hit else "unknown",
        ))

    # Entry valuation ceiling.
    if thesis.valuation_cap:
        cap = _to_usd(thesis.valuation_cap.replace("$", ""))
        realized = _find_valuation_usd(blob)
        if realized is None or cap is None:
            out.append(MandateConstraint("Valuation ceiling", thesis.valuation_cap, "not disclosed" if realized is None else f"${_human_usd(realized)}", "unknown"))
        elif realized <= cap:
            out.append(MandateConstraint("Valuation ceiling", thesis.valuation_cap, f"${_human_usd(realized)}", "met"))
        else:
            out.append(MandateConstraint("Valuation ceiling", thesis.valuation_cap, f"${_human_usd(realized)}", "gap"))

    # Instrument.
    if thesis.instrument:
        want = thesis.instrument.lower()
        if want in blob.lower() or ("safe" in want and "safe" in blob.lower()):
            out.append(MandateConstraint("Instrument", thesis.instrument, thesis.instrument, "met"))
        else:
            out.append(MandateConstraint("Instrument", thesis.instrument, "not disclosed", "unknown"))

    return out


def render_mandate_fit(constraints: list[MandateConstraint]) -> str:
    """Render the Mandate-fit block as memo prose (one gated line per constraint)."""
    if not constraints:
        return ""
    lines = [
        f"- [{c.status}] {c.label} - mandate: {c.target} | realized: {c.realized}"
        for c in constraints
    ]
    return "\n".join(lines)
