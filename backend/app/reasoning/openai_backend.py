"""OpenAI structured-output reasoning backend (the product path).

* Screening runs on the cheap model (gpt-4o-mini): one call, viable vs non-viable.
* Each axis runs on gpt-4o as a *separate* structured-output call, so evidence
  stays scoped per axis and one axis can never leak into another's rationale.

Token usage is accumulated so the caller can print a cost estimate. Evidence-id
validation lives in the service, not here - both backends are validated the same
way.
"""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel

from app.config import OPENAI_API_KEY
from app.reasoning.backend import ReasoningBackend
from app.reasoning.context import ScoringContext, render_signals
from app.reasoning.mandate import FOUNDER_SUCCESS_RUBRIC
from app.reasoning.schemas import AxisResult, ColdStartAxisResult, ScreeningResult

SCREEN_MODEL = "gpt-4o-mini"
AXIS_MODEL = "gpt-4o"

# USD per 1M tokens (published list prices; used only for a rough run estimate).
_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

_SYSTEM = (
    "You are a disciplined pre-seed VC analyst. You reason only from the evidence "
    "provided, never invent facts, and you always evaluate relative to the fund's "
    "thesis. When you cite evidence, cite only the signal_id values shown to you."
)


class _Usage:
    """Process-wide token accumulator + cost estimate."""

    def __init__(self) -> None:
        self.by_model: dict[str, list[int]] = {}

    def add(self, model: str, prompt: int, completion: int) -> None:
        row = self.by_model.setdefault(model, [0, 0])
        row[0] += prompt
        row[1] += completion

    def estimate_usd(self) -> float:
        total = 0.0
        for model, (p, c) in self.by_model.items():
            in_price, out_price = _PRICING.get(model, (0.0, 0.0))
            total += p / 1_000_000 * in_price + c / 1_000_000 * out_price
        return round(total, 4)

    def report(self) -> dict:
        return {
            "by_model": {
                m: {"prompt": v[0], "completion": v[1]} for m, v in self.by_model.items()
            },
            "estimated_usd": self.estimate_usd(),
        }


USAGE = _Usage()


def _thesis_line(ctx: ScoringContext) -> str:
    return f"FUND THESIS (evaluate relative to this):\n{ctx.thesis_rationale}"


def _company_line(ctx: ScoringContext) -> str:
    c = ctx.company
    return (
        f"COMPANY: {c.name} | sector={c.sector} | stage={c.stage} | geo={c.geography}\n"
        f"ONE-LINER: {c.one_liner or '(none)'}"
    )


def _founders_line(ctx: ScoringContext) -> str:
    parts = []
    for f in ctx.founders:
        parts.append(
            f"- {f.name}: {f.bio or '(no bio)'} | persistent founder_score="
            f"{f.founder_score if f.founder_score is not None else 'unset'} | "
            f"prior score_history={f.score_history or '[]'}"
        )
    return "FOUNDERS:\n" + ("\n".join(parts) if parts else "(none)")


def _team_block(ctx: ScoringContext) -> str:
    """Per-founder dossier for team-complementarity reasoning: identity + persistent
    score + individual cold-start flag + that founder's own grouped signals."""
    lines = []
    for f in ctx.founders:
        sigs = ctx.signals_for(f.id)
        cold = ctx.founder_cold_start.get(f.id)
        lines.append(
            f"- {f.name} | founder_score="
            f"{f.founder_score if f.founder_score is not None else 'unset'} | "
            f"cold_start={'yes' if cold else 'no'} | prior_companies={len(f.companies)}\n"
            f"  bio: {f.bio or '(no bio)'}\n"
            f"  signals: {render_signals(sigs) if sigs else '(none - thin individual record)'}"
        )
    solo = (
        " -- SOLO FOUNDER: treat as a flagged risk with rationale, NEVER an automatic penalty"
        if len(ctx.founders) <= 1
        else ""
    )
    return f"TEAM ({len(ctx.founders)} founder(s)){solo}:\n" + ("\n".join(lines) if lines else "(none)")


def _guidance_block(ctx: ScoringContext, axis: str | None = None) -> str:
    """The mandate fund-guidance (+ per-axis emphasis) injected into a prompt, or ''."""
    parts: list[str] = []
    if ctx.mandate_guidance:
        parts.append("FUND GUIDANCE (from the mandate - weigh, but never override the "
                     "three-axis discipline, trust levels, or diligence honesty):\n"
                     + ctx.mandate_guidance)
    note = ctx.axis_notes.get(axis or "", "")
    if note:
        parts.append(f"AXIS EMPHASIS ({axis}): {note}")
    return "\n\n".join(parts)


def _join(*blocks: str) -> str:
    return "\n\n".join(b for b in blocks if b)


class OpenAIBackend(ReasoningBackend):
    name = AXIS_MODEL

    def __init__(self) -> None:
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=OPENAI_API_KEY)
        return self._client

    def _parse(self, model: str, system: str, user: str, schema: type[BaseModel]):
        completion = self.client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=schema,
            temperature=0.2,
        )
        if completion.usage is not None:
            USAGE.add(
                model,
                completion.usage.prompt_tokens,
                completion.usage.completion_tokens,
            )
        return completion.choices[0].message.parsed

    def screen(self, ctx: ScoringContext) -> ScreeningResult:
        user = _join(
            _thesis_line(ctx),
            _guidance_block(ctx),
            _company_line(ctx),
            _founders_line(ctx),
            f"DECK (excerpt): {ctx.deck_text[:1500] or '(no deck)'}",
            f"SIGNALS:\n{render_signals(ctx.company_signals + ctx.founder_signals)}",
            "Fast first-pass screen: is this clearly non-viable (no real problem, no "
            "wedge, pure buzzword, or hopeless team) or is it worth full 3-axis "
            "analysis? Apply any mandate gates in the fund guidance above (e.g. an "
            "exclusion, or a hard traction gate that is clearly and irrecoverably "
            "missed). Be decisive but fair - thin evidence alone is NOT non-viable.",
        )
        return self._parse(SCREEN_MODEL, _SYSTEM, user, ScreeningResult)

    def score_founder(self, ctx: ScoringContext) -> AxisResult:
        user = _join(
            _thesis_line(ctx),
            _guidance_block(ctx, "founder"),
            _company_line(ctx),
            _team_block(ctx),
            FOUNDER_SUCCESS_RUBRIC,
            "Score the FOUNDER axis (1-10) for the TEAM as a whole. Assess explicitly: "
            "(a) individual strength per founder from their signals + persistent "
            "founder_score; (b) COMPLEMENTARITY - is technical AND commercial ground "
            "covered, where do domain expertises overlap vs leave gaps, is there any "
            "prior-collaboration signal; (c) team completeness relative to the idea (a "
            "deep-tech idea with no technical founder is an explicit gap); (d) a solo "
            "founder is a flagged risk with rationale, never an automatic penalty. A mix "
            "of one track-record founder and one cold-start co-founder does NOT zero the "
            "team - note per-founder confidence. Name the complementarity verdict in the "
            "rationale and cite per-founder evidence_signal_ids. Set trend from the "
            "trajectory of the evidence.",
        )
        return self._parse(AXIS_MODEL, _SYSTEM, user, AxisResult)

    def score_founder_cold_start(self, ctx: ScoringContext) -> ColdStartAxisResult:
        user = _join(
            _thesis_line(ctx),
            _guidance_block(ctx, "founder"),
            _company_line(ctx),
            _team_block(ctx),
            FOUNDER_SUCCESS_RUBRIC,
            f"DECK (excerpt): {ctx.deck_text[:1500] or '(no deck)'}",
            "This TEAM is COLD-START: every founder has little/no external track record. "
            "Do NOT default to a low score for thin evidence. Score the team's POTENTIAL "
            "on: (1) deck writing quality, (2) domain-insight specificity, (3) learning "
            "velocity (anything shipped, how fast), (4) problem-founder fit, and (5) "
            "COMPLEMENTARITY - technical vs commercial coverage and gaps relative to the "
            "idea (a solo founder is a flagged risk, not an automatic penalty). Name the "
            "complementarity verdict. Return a SCORE RANGE [low, high] reflecting genuine "
            "uncertainty and keep confidence low. Cite per-founder evidence_signal_ids.",
        )
        return self._parse(AXIS_MODEL, _SYSTEM, user, ColdStartAxisResult)

    def score_market(self, ctx: ScoringContext) -> AxisResult:
        user = _join(
            _thesis_line(ctx),
            _guidance_block(ctx, "market"),
            _company_line(ctx),
            f"DECK (excerpt): {ctx.deck_text[:1500] or '(no deck)'}",
            f"COMPANY SIGNALS (cite these ids):\n{render_signals(ctx.company_signals)}",
            "Score the MARKET axis (1-10): sizing, competitors, SWOT. Reflect a "
            "bullish / neutral / bear stance in the score and rationale. Cite "
            "evidence_signal_ids.",
        )
        return self._parse(AXIS_MODEL, _SYSTEM, user, AxisResult)

    def score_idea(self, ctx: ScoringContext) -> AxisResult:
        user = _join(
            _thesis_line(ctx),
            _guidance_block(ctx, "idea_vs_market"),
            _company_line(ctx),
            _founders_line(ctx),
            f"DECK (excerpt): {ctx.deck_text[:1500] or '(no deck)'}",
            f"COMPANY SIGNALS (cite these ids):\n{render_signals(ctx.company_signals)}",
            "Score the IDEA-VS-MARKET axis (1-10): does the idea survive scrutiny "
            "as-is, or is the team strong enough to pivot into the real opportunity? "
            "A weak idea with a strong, adaptable team can still score moderately. "
            "Cite evidence_signal_ids.",
        )
        return self._parse(AXIS_MODEL, _SYSTEM, user, AxisResult)
