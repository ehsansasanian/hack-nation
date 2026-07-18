"""Draft outreach messages for outbound candidates (the "Activate" step).

Template-based and deterministic: it personalizes from concrete, already-stored
signals (repo name + stars + velocity, or Show HN points + linked domain) so the
draft cites real evidence rather than generic flattery. These are ALWAYS drafts -
nothing is sent anywhere; the banner makes that explicit.
"""

from __future__ import annotations

from app.models import Company, Founder, Signal, Thesis

_DRAFT_BANNER = "[DRAFT - review before sending; nothing is sent automatically]"


def _first_name(founder: Founder) -> str:
    name = (founder.name or founder.github_handle or "there").strip()
    return name.split()[0] if name and name[0].isalpha() else name


def _pick_signal(signals: list[Signal], source: str) -> Signal | None:
    matches = [s for s in signals if s.source == source]
    if not matches:
        return None
    return max(matches, key=lambda s: s.content.get("stars", s.content.get("points", 0)))


def _thesis_phrase(thesis: Thesis | None) -> str:
    if thesis and thesis.sectors:
        sectors = ", ".join(thesis.sectors[:3])
        stage = (thesis.stages or ["early-stage"])[0]
        return f"{stage} {sectors} founders"
    return "technical founders building at the infrastructure layer"


def draft_outreach(
    founder: Founder,
    company: Company,
    signals: list[Signal],
    thesis: Thesis | None,
    best_axis: str,
    best_score: float,
) -> str:
    """Return a personalized draft outreach message grounded in concrete signals."""
    hook = _hook(company, signals)
    body = (
        f"Hi {_first_name(founder)},\n\n"
        f"{hook} We back {_thesis_phrase(thesis)}, and {company.name} is exactly the "
        f"kind of {company.sector or 'technical'} work we track early. Our read scored it "
        f"strongest on the {best_axis.replace('_', ' ')} axis ({best_score}/10) from public signals alone.\n\n"
        f"Would you be open to a 20-minute call to hear where you're taking it? No deck needed.\n\n"
        f"- The VC Brain sourcing desk\n\n"
        f"{_DRAFT_BANNER}"
    )
    return body


def _hook(company: Company, signals: list[Signal]) -> str:
    gh = _pick_signal(signals, "github")
    if gh is not None:
        c = gh.content
        return (
            f"I came across {c.get('repo', company.name)} - {c.get('stars', 0):,} stars "
            f"at ~{c.get('stars_per_day', 0)}/day since launch, with "
            f"{_cadence_phrase(c)}. That velocity stood out."
        )
    hn = _pick_signal(signals, "hn")
    if hn is not None:
        c = hn.content
        domain = f" ({c['linked_domain']})" if c.get("linked_domain") else ""
        return (
            f"I saw your Show HN launch{domain} hit {c.get('points', 0)} points "
            f"(~{c.get('points_per_day', 0)}/day) - strong early signal from a tough crowd."
        )
    return f"I came across {company.name} and wanted to reach out."


def _cadence_phrase(content: dict) -> str:
    cadence = content.get("commit_cadence") or {}
    rate = cadence.get("commits_per_day")
    if rate:
        return f"~{rate} commits/day"
    return "active development"
