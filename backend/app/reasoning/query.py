"""Phase 4 natural-language pipeline query.

``run_query`` turns a compound query like "technical founder, Berlin, AI infra,
no prior VC backing" into structured filters (via the LLM parser, with the
deterministic offline parser as fallback), applies them as a hard filter over the
pipeline, then reranks the survivors and attaches a per-result match rationale -
one pass, not five manual filters. If the hard filter is too tight to fill the
result set, near-misses are appended and clearly marked as partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Application, Company, Founder
from app.reasoning.diligence_backend import get_diligence_backend
from app.reasoning.diligence_schemas import ParsedQuery

_EUROPE = {"berlin", "vienna", "london", "paris", "amsterdam", "munich", "germany", "austria", "uk"}
_TECH_BIO = ("engineer", "developer", "infra", "ml ", "machine learning", "researcher",
             "robotics", "data ", "scientist", "backend", "systems", "phd")


@dataclass(slots=True)
class QueryMatch:
    application_id: int
    company: str
    sector: str | None
    geography: str | None
    stage: str | None
    scores: dict[str, float]
    match_score: float
    partial: bool
    rationale: str


@dataclass(slots=True)
class QueryResult:
    query: str
    parsed: ParsedQuery
    backend: str
    results: list[QueryMatch] = field(default_factory=list)
    fallback_from: str | None = None


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def _geo_match(company_geo: str | None, wanted: str) -> bool:
    cg, w = _norm(company_geo), _norm(wanted)
    if not cg:
        return False
    if w == "europe":
        return cg in _EUROPE
    return w == cg


def _technical(app: Application) -> tuple[bool, str]:
    for f in app.company.founders:
        if f.github_handle:
            return True, f"github: {f.github_handle}"
        bio = _norm(f.bio)
        for kw in _TECH_BIO:
            if kw.strip() in bio:
                return True, f"'{kw.strip()}' in founder bio"
    return False, ""


def _no_prior_vc(app: Application) -> tuple[bool, str]:
    # Prior VC backing = a real exit / raised round in the record. A raise that
    # diligence contradicted does NOT count as backing.
    for f in app.company.founders:
        hist = " ".join(str(e.get("note", "")) for e in (f.score_history or [])).lower()
        if "acquir" in _norm(f.bio) or "acquir" in hist or "raised" in hist:
            return False, ""
    contradicted_raise = next(
        (c for c in app.claims
         if c.trust_level == "contradicted"
         and any(t in _norm(c.text) for t in ("seed", "raised", "round", "funding"))),
        None,
    )
    if contradicted_raise is not None:
        return True, f"the '{contradicted_raise.text[:40]}...' raise was contradicted in diligence"
    return True, "no verified funding round on record"


def _enterprise_traction(app: Application) -> tuple[bool, str]:
    for c in app.claims:
        if (
            c.category == "traction"
            and c.trust_level in ("verified", "consistent")
            and any(t in _norm(c.text) for t in ("enterprise", "customer", "design partner", "production"))
        ):
            return True, f"'{c.text[:40]}...' ({c.trust_level})"
    return False, ""


def _repeat_founder(app: Application) -> tuple[bool, str]:
    for f in app.company.founders:
        if len(f.companies) > 1 or any(
            t in _norm(f.bio) for t in ("second-time", "serial", "previously founded", "acquired")
        ):
            return True, f"{f.name} has prior-startup history"
    return False, ""


_ATTRIBUTE_MATCHERS = {
    "technical founder": _technical,
    "non-technical founder": lambda a: (not _technical(a)[0], "no technical signal on the founder"),
    "no prior vc backing": _no_prior_vc,
    "enterprise traction": _enterprise_traction,
    "repeat founder": _repeat_founder,
    "first-time founder": lambda a: (not _repeat_founder(a)[0], "no prior-startup history"),
    "open source": lambda a: (
        any(f.github_handle for f in a.company.founders),
        "public code on github",
    ),
}


def run_query(
    session: Session,
    query: str,
    prefer_backend: str | None = None,
    limit: int = 8,
    allow_fallback: bool = True,
) -> QueryResult:
    backend = get_diligence_backend(prefer_backend)
    fallback_from: str | None = None
    try:
        parsed = backend.parse_query(query)
        backend_name = backend.name
    except OpenAIError as exc:
        if not (allow_fallback and backend.name != "offline-deterministic"):
            raise
        backend = get_diligence_backend("offline")
        parsed = backend.parse_query(query)
        backend_name = backend.name
        fallback_from = f"openai ({type(exc).__name__})"

    apps = list(
        session.scalars(
            select(Application).options(
                selectinload(Application.company)
                .selectinload(Company.founders)
                .selectinload(Founder.companies),
                selectinload(Application.scores),
                selectinload(Application.claims),
            )
        )
    )

    ranked = _rank(apps, parsed, limit)
    return QueryResult(
        query=query, parsed=parsed, backend=backend_name, results=ranked, fallback_from=fallback_from
    )


def _rank(apps: list[Application], parsed: ParsedQuery, limit: int) -> list[QueryMatch]:
    specified = {
        "sector": bool(parsed.sector),
        "geo": bool(parsed.geography),
        "stage": bool(parsed.stage),
    }
    strict: list[QueryMatch] = []
    partial: list[QueryMatch] = []

    for app in apps:
        c = app.company
        sector_ok = _norm(c.sector) == _norm(parsed.sector) if specified["sector"] else False
        geo_ok = _geo_match(c.geography, parsed.geography) if specified["geo"] else False
        stage_ok = _norm(c.stage) == _norm(parsed.stage) if specified["stage"] else False

        matched: list[str] = []
        missed: list[str] = []
        if specified["sector"]:
            (matched if sector_ok else missed).append(f"sector {parsed.sector}")
        if specified["geo"]:
            (matched if geo_ok else missed).append(f"geography {parsed.geography}")
        if specified["stage"]:
            (matched if stage_ok else missed).append(f"stage {parsed.stage}")

        attr_score = 0
        for attr in parsed.attributes:
            matcher = _ATTRIBUTE_MATCHERS.get(attr.strip().lower())
            if matcher is None:
                continue
            ok, why = matcher(app)
            if ok:
                attr_score += 1
                matched.append(f"{attr}" + (f" ({why})" if why else ""))
            else:
                missed.append(attr)

        scores = {s.axis: s.value for s in app.scores}
        best = max(scores.values(), default=0.0)
        score = (
            3 * sector_ok + 3 * geo_ok + 2 * stage_ok + 2 * attr_score + 0.1 * best
        )

        hard_ok = all([
            not specified["sector"] or sector_ok,
            not specified["geo"] or geo_ok,
            not specified["stage"] or stage_ok,
        ])
        rationale = _rationale(matched, missed)
        match = QueryMatch(
            application_id=app.id, company=c.name, sector=c.sector, geography=c.geography,
            stage=c.stage, scores=scores, match_score=round(score, 2),
            partial=not hard_ok, rationale=rationale,
        )
        if hard_ok:
            strict.append(match)
        elif sector_ok or attr_score:  # a near-miss worth surfacing
            partial.append(match)

    strict.sort(key=lambda x: x.match_score, reverse=True)
    partial.sort(key=lambda x: x.match_score, reverse=True)
    results = strict + partial[: max(0, limit - len(strict))]
    return results[:limit]


def _rationale(matched: list[str], missed: list[str]) -> str:
    parts = [f"{m} ✓" for m in matched] + [f"{m} ✗" for m in missed]
    return " · ".join(parts) if parts else "no criteria specified"
