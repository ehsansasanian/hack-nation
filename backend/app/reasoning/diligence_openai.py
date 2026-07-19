"""OpenAI structured-output diligence backend (Phase 4 product path).

Mirrors ``reasoning/openai_backend.py``: cheap model (gpt-4o-mini) for the
mechanical passes (claim extraction, query parsing), gpt-4o for the judgement
passes (truth-gap, validator, memo). Token usage is accumulated into the shared
``USAGE`` counter so one run reports a single cost estimate. Evidence-id
validation is done by the orchestrator, identically for both backends.
"""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel

from app.config import OPENAI_API_KEY
from app.reasoning.diligence_backend import DiligenceBackend
from app.reasoning.diligence_context import DiligenceContext, render_evidence
from app.reasoning.diligence_schemas import (
    ClaimAssessment,
    ClaimAssessments,
    ExtractedClaim,
    ExtractedClaims,
    MemoSections,
    ParsedQuery,
    ValidatorReport,
)
from app.reasoning.openai_backend import USAGE

CHEAP_MODEL = "gpt-4o-mini"
JUDGE_MODEL = "gpt-4o"

_SYSTEM = (
    "You are a disciplined pre-seed VC diligence analyst. You reason only from the "
    "evidence provided, never invent facts, and when you cite evidence you cite only "
    "the signal_id values shown to you. You are adversarial about claims: a claim is "
    "'contradicted' only when a signal actually conflicts, 'verified' only when a "
    "signal actually confirms."
)


def _claim_sources_block(ctx: DiligenceContext) -> str:
    lines = []
    for src in ctx.claim_sources:
        lines.append(f"[source={src.source}] {src.text[:1200]}")
    return "\n".join(lines) or "(no self-asserted claim sources)"


def _claims_block(claims: list[ExtractedClaim]) -> str:
    return "\n".join(f"- ({c.category}/{c.source}) {c.text}" for c in claims) or "(none)"


def _founders_block(ctx: DiligenceContext) -> str:
    """Resolved founders + the enrichment sources on file, so TEAM claims (e.g.
    'team of 5', 'ex-FAANG engineers') can be cross-referenced per founder."""
    if not ctx.founders:
        return "(no founders resolved)"
    by_founder: dict[int, list[str]] = {}
    for s in ctx.evidence_signals:
        if s.founder_id is not None:
            by_founder.setdefault(s.founder_id, []).append(f"{s.source}#{s.id}")
    lines = []
    for f in ctx.founders:
        srcs = ", ".join(by_founder.get(f.id, [])) or "no external evidence fetched"
        lines.append(f"- {f.name} ({(f.bio or 'no bio').split('.')[0]}) | enrichment: {srcs}")
    return "\n".join(lines)


class OpenAIDiligenceBackend(DiligenceBackend):
    name = JUDGE_MODEL

    def __init__(self) -> None:
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=OPENAI_API_KEY)
        return self._client

    def _parse(self, model: str, user: str, schema: type[BaseModel]):
        completion = self.client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format=schema,
            temperature=0.1,
        )
        if completion.usage is not None:
            USAGE.add(model, completion.usage.prompt_tokens, completion.usage.completion_tokens)
        return completion.choices[0].message.parsed

    def extract_claims(self, ctx: DiligenceContext) -> list[ExtractedClaim]:
        user = (
            f"COMPANY: {ctx.company.name} ({ctx.company.sector})\n\n"
            f"SELF-ASSERTED CLAIM SOURCES (deck + public posts):\n{_claim_sources_block(ctx)}\n\n"
            "Extract the discrete, checkable claims the company/founder asserts about "
            "themselves. Categorise each as traction / revenue / team / market and record "
            "which source it came from. Skip the problem narrative and the funding ask."
        )
        return list(self._parse(CHEAP_MODEL, user, ExtractedClaims).claims)

    def assess_claims(
        self, ctx: DiligenceContext, claims: list[ExtractedClaim]
    ) -> list[ClaimAssessment]:
        user = (
            f"COMPANY: {ctx.company.name}\n\n"
            f"FOUNDERS ON FILE (cross-reference TEAM claims against each founder's "
            f"enrichment signals):\n{_founders_block(ctx)}\n\n"
            f"CLAIMS TO CHECK:\n{_claims_block(claims)}\n\n"
            f"EVIDENCE SIGNALS (cite these signal_ids):\n{render_evidence(ctx.evidence_signals)}\n\n"
            "For each claim assign a trust_level:\n"
            "- verified: a specific signal confirms it (cite that signal_id).\n"
            "- consistent: nothing contradicts it and it is plausible.\n"
            "- unverified: NO signal speaks to it either way. Absence of evidence is "
            "ALWAYS 'unverified', NEVER 'contradicted'.\n"
            "- contradicted: a specific signal DIRECTLY conflicts with the claim. This is "
            "allowed ONLY when you can (a) put that conflicting signal_id in "
            "evidence_signal_ids, and (b) write a contradiction_note that quotes the "
            "signal_id and its conflicting content next to the claim text, e.g. \"Claim "
            "'X' conflicts with signal_id=14 which states 'Y'.\" If you cannot point to "
            "such a signal, the claim is 'unverified', not 'contradicted'.\n"
            "Cite evidence_signal_ids for every verified/contradicted verdict. Return one "
            "assessment per claim, in order."
        )
        return list(self._parse(JUDGE_MODEL, user, ClaimAssessments).assessments)

    def validate(
        self, ctx: DiligenceContext, assessments: list[ClaimAssessment]
    ) -> ValidatorReport:
        axes = "\n".join(
            f"- axis={s.axis} score={s.value} evidence={s.evidence_signal_ids} "
            f"rationale={s.rationale}"
            for s in ctx.scores
        ) or "(no scores)"
        claims = "\n".join(
            f"[{i}] ({a.category}) trust={a.trust_level} evidence={a.evidence_signal_ids} {a.text}"
            for i, a in enumerate(assessments)
        ) or "(none)"
        user = (
            f"COMPANY: {ctx.company.name}\n\n"
            f"EVIDENCE SIGNALS:\n{render_evidence(ctx.evidence_signals)}\n\n"
            f"AXIS RATIONALES:\n{axes}\n\n"
            f"ASSESSED CLAIMS:\n{claims}\n\n"
            "Self-correction pass. For each axis, try to REFUTE the rationale: is it "
            "actually supported by the cited signals? Set supported=false and explain if "
            "not. For each claim, re-check its trust_level against the cited evidence and "
            "DOWNGRADE (never upgrade) if it is over-optimistic; keep legitimate "
            "contradictions. A claim marked 'contradicted' that does NOT cite a specific "
            "conflicting signal_id (empty evidence) or whose note does not quote that "
            "signal must be revised to 'unverified' - absence of evidence is not a "
            "contradiction. Reference the 0-based claim index."
        )
        return self._parse(JUDGE_MODEL, user, ValidatorReport)

    def write_memo(
        self, ctx: DiligenceContext, assessments: list[ClaimAssessment]
    ) -> MemoSections:
        scores = "\n".join(
            f"- {s.axis}: {s.value}/10 (confidence {s.confidence}) - {s.rationale}"
            for s in ctx.scores
        ) or "(not scored)"
        claims = "\n".join(f"- [{a.trust_level}] ({a.category}) {a.text}" for a in assessments) or "(none)"
        user = (
            f"COMPANY: {ctx.company.name} | {ctx.company.sector} | {ctx.company.stage} | "
            f"{ctx.company.geography}\nONE-LINER: {ctx.company.one_liner}\n\n"
            f"THESIS FIT: {ctx.thesis_rationale}\n\n"
            f"3-AXIS SCORES (never average these):\n{scores}\n\n"
            f"CLAIMS WITH TRUST LEVELS:\n{claims}\n\n"
            f"EVIDENCE SIGNALS:\n{render_evidence(ctx.evidence_signals)}\n\n"
            f"DECK EXCERPT:\n{ctx.deck_text[:1500] or '(no deck)'}\n\n"
            "Write a TIGHT investment memo. Fill EVERY field:\n"
            "- company_snapshot, investment_hypotheses, swot, problem_and_product, "
            "traction_and_kpis: evidence-backed. Render every claim with its trust level. "
            "Do NOT fabricate financials.\n"
            "- technology_defensibility: assess proprietary-vs-commoditizable from the deck "
            "+ signals; name the moat type if any. An assessment, not invented benchmarks.\n"
            "- market_sizing: give top-down AND/OR bottom-up sizing and STATE YOUR "
            "ASSUMPTIONS EXPLICITLY. Mark any deck figure as claimed/unverified; never "
            "invent a market number or cite a database we do not have.\n"
            "- competition: name competitor CLUSTERS (incumbents, open-source, big-tech "
            "platforms, point-solution startups) as analysis, plus any competitors the deck "
            "names.\n"
            "- exit_perspective: plausible exit paths (strategic acquirer archetypes, IPO "
            "conditions), CLEARLY LABELED as a hypothesis; directional only.\n"
            "No padding - every line must earn its place."
        )
        return self._parse(JUDGE_MODEL, user, MemoSections)

    def parse_query(self, query: str) -> ParsedQuery:
        user = (
            f"Parse this compound VC-pipeline search into structured filters:\n\"{query}\"\n\n"
            "sector (AI infra / fintech / health / devtools or empty), geography (city/region "
            "or empty), stage (pre-seed / seed / ... or empty), and a list of founder/company "
            "attributes such as 'technical founder', 'no prior vc backing', 'enterprise traction'."
        )
        return self._parse(CHEAP_MODEL, user, ParsedQuery)
