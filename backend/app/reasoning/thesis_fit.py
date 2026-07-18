"""Thesis engine: hard filter + fit rationale injected into every scoring prompt.

The hard filter is deterministic (no LLM) - an out-of-scope sector/stage/geo is a
config decision, not a judgement call. An empty thesis dimension means "no
constraint on that dimension", so a partially-configured thesis stays permissive.
The rationale string is the connective tissue: it is threaded into all three axis
prompts so scoring always reasons *relative to* the fund's mandate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Company, Thesis


@dataclass(slots=True)
class ThesisFit:
    in_scope: bool
    out_of_scope_reasons: list[str] = field(default_factory=list)
    rationale: str = ""


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _matches(value: str | None, allowed: list[str]) -> bool:
    """Empty allow-list = no constraint. Otherwise case-insensitive membership."""
    if not allowed:
        return True
    return _norm(value) in {_norm(a) for a in allowed}


def thesis_fit(company: Company, thesis: Thesis | None) -> ThesisFit:
    if thesis is None:
        return ThesisFit(
            in_scope=True,
            rationale="No thesis configured; scoring proceeds without a mandate filter.",
        )

    reasons: list[str] = []
    if not _matches(company.sector, thesis.sectors):
        reasons.append(
            f"sector '{company.sector}' outside thesis sectors {thesis.sectors}"
        )
    if not _matches(company.stage, thesis.stages):
        reasons.append(f"stage '{company.stage}' outside thesis stages {thesis.stages}")
    if not _matches(company.geography, thesis.geographies):
        reasons.append(
            f"geography '{company.geography}' outside thesis geographies {thesis.geographies}"
        )

    in_scope = not reasons
    rationale = _build_rationale(company, thesis, in_scope, reasons)
    return ThesisFit(in_scope=in_scope, out_of_scope_reasons=reasons, rationale=rationale)


def _build_rationale(
    company: Company, thesis: Thesis, in_scope: bool, reasons: list[str]
) -> str:
    mandate = (
        f"Thesis '{thesis.name}': sectors={thesis.sectors or 'any'}, "
        f"stages={thesis.stages or 'any'}, geographies={thesis.geographies or 'any'}, "
        f"check={thesis.check_size or 'n/a'}, risk_appetite={thesis.risk_appetite or 'n/a'}."
    )
    subject = (
        f"{company.name} is {company.sector or 'unknown-sector'} / "
        f"{company.stage or 'unknown-stage'} / {company.geography or 'unknown-geo'}."
    )
    if not in_scope:
        return f"{mandate} {subject} OUT OF SCOPE: {'; '.join(reasons)}."
    core = _is_core_sector(company.sector, thesis.sectors)
    fit = "core-sector fit" if core else "in-scope (adjacent sector)"
    return f"{mandate} {subject} Thesis fit: {fit} on all hard filters."


def _is_core_sector(sector: str | None, sectors: list[str]) -> bool:
    """First listed sector(s) are treated as the fund's primary focus."""
    if not sectors:
        return False
    return _norm(sector) == _norm(sectors[0])
