"""Deterministic, network-free diligence backend (Phase 4).

Same contract as the OpenAI diligence backend, implemented with transparent
heuristics over the *same* prepared ``DiligenceContext`` so the whole diligence /
memo / query flow runs with the network off and gives a reproducible demo
baseline. Provenance is stamped as ``offline-deterministic`` on everything it
produces.

The logic is intentionally general (keyword + metric + negation heuristics), not
hardcoded to the synthetic decks: a claim is any quantified/assertive statement
mapped to traction / revenue / team / market; the truth-gap cross-references each
claim against the stored evidence signals (private diligence notes + objective
metrics) and only calls something ``contradicted`` when a signal actually
conflicts, or ``verified`` when a signal actually confirms.
"""

from __future__ import annotations

import re

from app.models import Signal
from app.reasoning.diligence_backend import DiligenceBackend
from app.reasoning.diligence_context import ClaimSource, DiligenceContext
from app.reasoning.diligence_schemas import (
    AxisCritique,
    ClaimAssessment,
    ClaimCritique,
    ExtractedClaim,
    MemoSections,
    ParsedQuery,
    ValidatorReport,
)

# --- claim categorisation ---------------------------------------------------

_TEAM_KW = (
    "team of", "team:", "co-founder", "cofounder", "engineers", "engineer",
    "designer", " gtm", "headcount", "employees", " ceo", " cto", "founder",
    "ex-", "phd", "researcher", "ex-deepmind", "ex-faang", "staff",
)
_REVENUE_KW = (
    "mrr", "arr", "revenue", "/month", "per month", "per seat", "payback",
    "gross margin", "margin", "ltv", "cac", "pricing", "$/", "unit economics",
)
_TRACTION_KW = (
    "customer", "customers", "users", "design partner", "design partners",
    "pilot", "pilots", "in production", "production", "waitlist", "stars",
    "contributors", "downloads", "tokens/day", "clearance", "fda", "live in",
    "signup", "sign-up", "growth", "growing", "month over month", "contracts",
    "deployment", "reference call", "raised", "seed round", "validation",
    "auroc", "prototype", "tested with", "partners", "paying",
)
_MARKET_KW = (
    "market", "tam", "sam", "billion", "$b", "opportunity", "spend",
    "market size", "addressable", "fastest-growing",
)
# Section headers under which lines are the fund's own ask, not a checkable claim.
_SKIP_HEADERS = {"ask", "the ask", "what i need", "the ask:"}

# Negation / confirmation vocabulary for the truth-gap.
_NEG_TERMS = (
    "not supported", "unsupported", "no submission", "no seed", "no round",
    "pre-revenue", "$0", "none paying", "no product", "no code", "not live",
    "no signed", "does not", "doesn't", "not on file", "no funding", "not found",
    "no evidence", "no seed round", "exploratory", "letter of intent", "no revenue",
)
_POS_TERMS = (
    "confirmed", "genuine", "appears genuine", "verified", "reference call",
    "in production", "checks out", "corroborat", "holds up", "acquired",
    "acquisition", "strong clinical signal",
)

_TOKEN_RE = re.compile(r"[a-z0-9$.,%/-]+")
_NUM_RE = re.compile(r"\$?\d[\d,]*\.?\d*\s?[kmb%]?", re.IGNORECASE)
_STOP = {
    "the", "and", "are", "our", "for", "with", "per", "not", "but", "you", "your",
    "they", "their", "than", "over", "under", "out", "more", "most", "less",
    "into", "across", "only", "this", "that", "from", "has", "have", "was", "were",
    "will", "can", "all", "any", "who", "how", "why", "what", "where", "team",
    "build", "building", "using", "use", "uses", "new", "one", "two", "its",
}


def _blob(*parts: str | None) -> str:
    return " ".join(p.lower() for p in parts if p)


def _hits(blob: str, terms: tuple[str, ...]) -> bool:
    return any(t in blob for t in terms)


def _categorize(text: str, header: str = "") -> str | None:
    b = _blob(text, header)
    money_or_customer = _hits(b, ("mrr", "arr", "revenue", "customer", "paying"))
    if _hits(b, _TEAM_KW) and not money_or_customer:
        return "team"
    if _hits(b, _REVENUE_KW):
        return "revenue"
    if _hits(b, _MARKET_KW) and not _hits(b, _TRACTION_KW):
        return "market"
    if _hits(b, _TRACTION_KW):
        return "traction"
    if _hits(b, _MARKET_KW):
        return "market"
    return None


def _has_metric(text: str) -> bool:
    return bool(_NUM_RE.search(text))


def _looks_like_header(line: str) -> bool:
    return len(line.split()) <= 4 and not _has_metric(line) and not line.endswith((".", "!"))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .-•*")


def _numbers(text: str) -> list[float]:
    out: list[float] = []
    for raw in _NUM_RE.findall(text.lower()):
        token = raw.strip().replace("$", "").replace(",", "").replace("%", "")
        mult = 1.0
        if token.endswith("k"):
            mult, token = 1_000, token[:-1]
        elif token.endswith("m"):
            mult, token = 1_000_000, token[:-1]
        elif token.endswith("b"):
            mult, token = 1_000_000_000, token[:-1]
        try:
            out.append(float(token) * mult)
        except ValueError:
            continue
    return out


def _is_yearish(n: float) -> bool:
    return 1990 <= n <= 2100 and float(n).is_integer()


def _all_numbers(text: str) -> set[int]:
    """Rounded numeric values a claim/note asserts (for value-overlap tests)."""
    return {round(n) for n in _numbers(text) if not _is_yearish(n)}


def _big_numbers(text: str) -> set[int]:
    """Non-trivial values (>= 10), used to detect a genuine value conflict."""
    return {n for n in _all_numbers(text) if n >= 10}


def _salient(text: str, drop: set[str]) -> set[str]:
    tokens: set[str] = set()
    for tok in _TOKEN_RE.findall(text.lower()):
        clean = tok.strip("$.,%/-")
        if not clean or clean in drop:
            continue
        if clean.isdigit():
            if len(clean) >= 2:  # drop trivial single-digit noise
                tokens.add(clean)
        elif len(clean) >= 3 and clean not in _STOP:
            tokens.add(clean)
    return tokens


def _drop_names(ctx: DiligenceContext) -> set[str]:
    drop: set[str] = set()
    for name in [ctx.company.name] + [f.name for f in ctx.founders]:
        drop.update(t for t in _TOKEN_RE.findall((name or "").lower()) if len(t) >= 3)
    return drop


# --- deck / signal extraction ----------------------------------------------


def _extract_from_deck(deck_text: str) -> list[tuple[str, str]]:
    header = ""
    claims: list[tuple[str, str]] = []
    for raw in deck_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_bullet = line[0] in "-•*"
        indented = raw[:1].isspace()
        text = line[1:].strip() if is_bullet else line

        # Continuation of a wrapped bullet: fold into the previous claim.
        if indented and not is_bullet and claims:
            merged_text, cat = claims[-1]
            claims[-1] = (_clean(f"{merged_text} {text}"), cat)
            continue
        if not is_bullet and _looks_like_header(line):
            header = line.lower()
            continue
        if header in _SKIP_HEADERS:
            continue

        cat = _categorize(text, header)
        if cat is None:
            continue
        # Non-bullet prose is only a claim if it carries a concrete metric,
        # so the problem narrative is not mistaken for a company claim.
        if not is_bullet and not _has_metric(text):
            continue
        claims.append((_clean(text), cat))
    return claims


class OfflineDiligenceBackend(DiligenceBackend):
    name = "offline-deterministic"

    # --- claim extraction --------------------------------------------------
    def extract_claims(self, ctx: DiligenceContext) -> list[ExtractedClaim]:
        seen: set[str] = set()
        out: list[ExtractedClaim] = []
        for src in ctx.claim_sources:
            for text, cat in self._claims_for_source(src):
                key = text.lower()
                if key in seen or len(text) < 6:
                    continue
                seen.add(key)
                out.append(ExtractedClaim(text=text, category=cat, source=src.source))
        return out[:12]  # keep the memo tight

    def _claims_for_source(self, src: ClaimSource) -> list[tuple[str, str]]:
        if src.source == "deck":
            return _extract_from_deck(src.text)
        cat = _categorize(src.text)
        if cat is None:
            return []
        return [(_clean(src.text), cat)]

    # --- truth-gap (per claim) --------------------------------------------
    def assess_claims(
        self, ctx: DiligenceContext, claims: list[ExtractedClaim]
    ) -> list[ClaimAssessment]:
        drop = _drop_names(ctx)
        manual = [s for s in ctx.evidence_signals if s.source == "manual"]
        metrics = [s for s in ctx.evidence_signals if s.source in ("github", "hn")]
        return [self._assess_one(c, manual, metrics, drop) for c in claims]

    def _assess_one(
        self, claim: ExtractedClaim, manual: list[Signal], metrics: list[Signal], drop: set[str]
    ) -> ClaimAssessment:
        claim_tokens = _salient(claim.text, drop)
        claim_all_nums = _all_numbers(claim.text)
        claim_big_nums = _big_numbers(claim.text)

        # 1. Contradiction, tied to THIS claim (never the whole category):
        #    (a) a seeded ``contradicts`` marker whose note also shares a term/value
        #        with the claim, or (b) a note that negates a value the claim asserts.
        for sig in manual:
            note = str(sig.content.get("note", ""))
            note_l = note.lower()
            note_tokens = _salient(note, drop)
            marker = sig.content.get("contradicts") == claim.category
            term_or_value_overlap = bool(
                (claim_tokens & note_tokens) or (claim_all_nums & _all_numbers(note))
            )
            value_conflict = bool(
                _hits(note_l, _NEG_TERMS) and (claim_big_nums & _big_numbers(note))
            )
            if (marker and term_or_value_overlap) or value_conflict:
                return ClaimAssessment(
                    text=claim.text,
                    category=claim.category,
                    source=claim.source,
                    trust_level="contradicted",
                    evidence_signal_ids=[sig.id],
                    contradiction_note=(
                        f"Claim ({claim.source}) \"{claim.text}\" conflicts with "
                        f"{sig.source} diligence [{sig.timestamp.date().isoformat()}]: \"{note}\""
                    ),
                )

        # 2. Verified: an objective metric matches, or a diligence note confirms.
        claim_nums = [n for n in _numbers(claim.text) if n >= 50 and not _is_yearish(n)]
        for sig in metrics:
            if _numbers_match(claim_nums, _signal_numbers(sig)):
                return ClaimAssessment(
                    text=claim.text, category=claim.category, source=claim.source,
                    trust_level="verified", evidence_signal_ids=[sig.id],
                )
        for sig in manual:
            note = str(sig.content.get("note", ""))
            # Confirmation needs a real overlap (>= 2 shared terms), so a single
            # generic domain word does not pass a claim off as verified.
            if len(claim_tokens & _salient(note, drop)) >= 2 and _hits(note.lower(), _POS_TERMS):
                return ClaimAssessment(
                    text=claim.text, category=claim.category, source=claim.source,
                    trust_level="verified", evidence_signal_ids=[sig.id],
                )

        # 3. Consistent (topically corroborated) vs unverified (nothing to check).
        related = [
            s for s in manual + metrics
            if claim_tokens & _salient(_signal_text(s), drop)
        ]
        if related:
            return ClaimAssessment(
                text=claim.text, category=claim.category, source=claim.source,
                trust_level="consistent", evidence_signal_ids=[s.id for s in related],
            )
        return ClaimAssessment(
            text=claim.text, category=claim.category, source=claim.source,
            trust_level="unverified", evidence_signal_ids=[],
        )

    # --- validator (self-correction) --------------------------------------
    def validate(
        self, ctx: DiligenceContext, assessments: list[ClaimAssessment]
    ) -> ValidatorReport:
        drop = _drop_names(ctx)
        evidence_by_id = {s.id: s for s in ctx.evidence_signals}
        contradicted_terms = {
            "traction": any(a.category == "traction" and a.trust_level == "contradicted" for a in assessments),
            "revenue": any(a.category == "revenue" and a.trust_level == "contradicted" for a in assessments),
        }

        axis_critiques = [
            self._critique_axis(score, contradicted_terms) for score in ctx.scores
        ]
        claim_critiques = [
            self._critique_claim(i, a, evidence_by_id, drop)
            for i, a in enumerate(assessments)
        ]
        return ValidatorReport(axis_critiques=axis_critiques, claim_critiques=claim_critiques)

    def _critique_axis(self, score, contradicted: dict[str, bool]) -> AxisCritique:
        rationale = (score.rationale or "").lower()
        credits_traction = "traction=yes" in rationale or "traction': yes" in rationale
        if credits_traction and (contradicted["traction"] or contradicted["revenue"]):
            return AxisCritique(
                axis=score.axis, supported=False,
                note=(
                    f"{score.axis} rationale credits traction, but a traction/revenue "
                    "claim was contradicted in diligence - score likely overstated."
                ),
            )
        if score.value >= 6 and not score.evidence_signal_ids:
            return AxisCritique(
                axis=score.axis, supported=False,
                note=f"{score.axis} scores {score.value} but cites no evidence signals.",
            )
        return AxisCritique(
            axis=score.axis, supported=True,
            note="Rationale consistent with cited evidence; no contradicted claim relied upon.",
        )

    def _critique_claim(
        self, index: int, a: ClaimAssessment, evidence_by_id: dict[int, Signal], drop: set[str]
    ) -> ClaimCritique:
        # Refute over-optimistic verdicts; never touch a legitimate contradiction.
        if a.trust_level in ("verified", "consistent") and not a.evidence_signal_ids:
            return ClaimCritique(
                index=index, revised_trust_level="unverified",
                note="Downgraded: no cited evidence actually substantiates this claim.",
            )
        if a.trust_level == "verified":
            claim_tokens = _salient(a.text, drop)
            claim_nums = [n for n in _numbers(a.text) if n >= 50]
            strong = any(
                _numbers_match(claim_nums, _signal_numbers(evidence_by_id[sid]))
                or (
                    evidence_by_id[sid].source == "manual"
                    and _hits(str(evidence_by_id[sid].content.get("note", "")).lower(), _POS_TERMS)
                    and (claim_tokens & _salient(_signal_text(evidence_by_id[sid]), drop))
                )
                for sid in a.evidence_signal_ids
                if sid in evidence_by_id
            )
            if not strong:
                return ClaimCritique(
                    index=index, revised_trust_level="consistent",
                    note="Downgraded verified->consistent: cited evidence is indirect, not confirmatory.",
                )
        return ClaimCritique(index=index, revised_trust_level=a.trust_level, note="")

    # --- memo prose --------------------------------------------------------
    def write_memo(
        self, ctx: DiligenceContext, assessments: list[ClaimAssessment]
    ) -> MemoSections:
        c = ctx.company
        by_axis = {s.axis: s for s in ctx.scores}
        founders = "; ".join(
            f"{f.name} ({(f.bio or 'no bio').split('.')[0]})" for f in ctx.founders
        ) or "not disclosed"

        snapshot = (
            f"{c.name} - {(c.one_liner or 'no one-liner on file').rstrip('.')}. "
            f"Sector {c.sector or 'n/a'}, stage {c.stage or 'n/a'}, geography {c.geography or 'n/a'}. "
            f"Founders: {founders}. {ctx.thesis_rationale}"
        )

        hyp = self._hypotheses(ctx, by_axis, assessments)
        swot = self._swot(ctx, by_axis, assessments)
        pnp = self._problem_product(ctx)
        kpis = self._kpis(assessments)
        return MemoSections(
            company_snapshot=snapshot,
            investment_hypotheses=hyp,
            swot=swot,
            problem_and_product=pnp,
            traction_and_kpis=kpis,
        )

    def _hypotheses(self, ctx, by_axis, assessments) -> str:
        lines: list[str] = []
        f = by_axis.get("founder")
        if f:
            band = f" (cold-start range {f.score_low}-{f.score_high})" if f.cold_start else ""
            lines.append(
                f"- Founder bet: scored {f.value}/10{band}. {f.rationale or ''}".strip()
            )
        m = by_axis.get("market")
        if m:
            lines.append(f"- Market bet: {m.value}/10. {m.rationale or ''}".strip())
        verified = [a for a in assessments if a.trust_level == "verified"]
        if verified:
            lines.append(
                "- Evidence base: "
                + "; ".join(a.text for a in verified[:3])
                + " (externally verified)."
            )
        return "\n".join(lines) or "- Insufficient signal for a hypothesis yet."

    def _swot(self, ctx, by_axis, assessments) -> str:
        strengths, weaknesses, threats = [], [], []
        for axis, s in by_axis.items():
            label = axis.replace("_", " ")
            if s.value >= 7:
                strengths.append(f"{label} {s.value}/10")
            elif s.value <= 4.5:
                weaknesses.append(f"{label} {s.value}/10")
        for a in assessments:
            if a.trust_level == "verified":
                strengths.append(f"verified: {a.text}")
            if a.trust_level == "contradicted":
                threats.append(f"contradicted claim: {a.text}")
        opportunities = [f"{ctx.company.sector or 'sector'} tailwind at {ctx.company.stage or 'pre-seed'}"]
        if ctx.cold_start:
            weaknesses.append("thin external track record (cold-start)")

        def _fmt(name: str, items: list[str]) -> str:
            return f"{name}: " + ("; ".join(items) if items else "none noted")

        return "\n".join([
            _fmt("Strengths", strengths[:4]),
            _fmt("Weaknesses", weaknesses[:4]),
            _fmt("Opportunities", opportunities),
            _fmt("Threats", threats[:4]),
        ])

    def _problem_product(self, ctx) -> str:
        if ctx.deck_text.strip():
            para = _first_paragraphs(ctx.deck_text, 2)
            return para or (ctx.company.one_liner or "Not described in the application.")
        return ctx.company.one_liner or "No deck on file; product described only via public signals."

    def _kpis(self, assessments) -> str:
        traction = [a for a in assessments if a.category in ("traction", "revenue")]
        if not traction:
            return "No traction or revenue KPIs stated in the application."
        verified = sum(a.trust_level == "verified" for a in traction)
        contradicted = sum(a.trust_level == "contradicted" for a in traction)
        return (
            f"{len(traction)} traction/revenue KPI(s) stated: {verified} externally "
            f"verified, {contradicted} contradicted by diligence. See claim-level "
            "trust levels below."
        )

    # --- NL query parse ----------------------------------------------------
    def parse_query(self, query: str) -> ParsedQuery:
        return _parse_query_offline(query)


# --- module-level signal helpers -------------------------------------------


def _signal_text(sig: Signal) -> str:
    parts = [str(v) for v in sig.content.values() if isinstance(v, (str, int, float))]
    return " ".join(parts)


def _signal_numbers(sig: Signal) -> list[float]:
    nums: list[float] = []
    for v in sig.content.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(float(v))
    nums.extend(_numbers(_signal_text(sig)))
    return nums


def _numbers_match(claim_nums: list[float], signal_nums: list[float]) -> bool:
    for cn in claim_nums:
        for sn in signal_nums:
            if sn <= 0 or _is_yearish(sn):
                continue
            if abs(cn - sn) / max(cn, sn) <= 0.05:  # within 5%
                return True
    return False


def _first_paragraphs(text: str, n: int) -> str:
    blocks = [b.strip().replace("\n", " ") for b in text.split("\n\n") if b.strip()]
    return " ".join(_clean(b) for b in blocks[1 : n + 1]) if len(blocks) > 1 else _clean(blocks[0]) if blocks else ""


# --- offline NL query parser ------------------------------------------------

_GEOS = (
    "berlin", "vienna", "london", "san francisco", "new york", "paris",
    "amsterdam", "munich", "europe", "germany", "austria", "uk",
)
_STAGES = ("pre-seed", "preseed", "seed", "series a", "series b", "series c")
_SECTOR_MAP = (
    ("ai infra", ("ai infra", "ai infrastructure", "inference", "llm", "ml infra", "gpu", "mlops")),
    ("fintech", ("fintech", "payments", "finance", "banking", "reconciliation")),
    ("health", ("health", "clinical", "medical", "healthcare", "biotech")),
    ("devtools", ("devtools", "developer tools", "developer-tools", "sdk", "cli")),
    ("AI infra", ("ai ", " ai", "artificial intelligence")),
)


def _parse_query_offline(query: str) -> ParsedQuery:
    q = f" {query.lower()} "
    sector = ""
    for canonical, kws in _SECTOR_MAP:
        if any(k in q for k in kws):
            sector = "AI infra" if canonical.lower() == "ai infra" else canonical
            break
    geography = next((g.title() if g not in ("uk",) else g.upper() for g in _GEOS if g in q), "")
    stage = next((s for s in _STAGES if s in q), "")

    attributes: list[str] = []
    if "technical founder" in q or "technical" in q:
        attributes.append("technical founder")
    if "non-technical" in q or "nontechnical" in q:
        attributes.append("non-technical founder")
    if "no prior vc" in q or "no vc" in q or "not vc-backed" in q or "no prior funding" in q or "bootstrapped" in q:
        attributes.append("no prior vc backing")
    if "enterprise" in q:
        attributes.append("enterprise traction")
    if "repeat founder" in q or "serial founder" in q or "prior exit" in q or "second-time" in q:
        attributes.append("repeat founder")
    if "cold start" in q or "first-time" in q or "first time" in q:
        attributes.append("first-time founder")
    if "open source" in q or "open-source" in q:
        attributes.append("open source")
    return ParsedQuery(sector=sector, geography=geography, stage=stage, attributes=attributes)
