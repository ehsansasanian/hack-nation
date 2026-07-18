"""Hacker News scanner via the Algolia HN Search API (no key required).

Pulls recent Show HN launches with real point traction, extracts the author,
points velocity and the linked product domain, and emits each as one
``RawSignal(source="hn")``. ``dedup_key`` is the immutable HN story id, so
re-scans never duplicate a launch even as its points keep climbing.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.ingestion.pipeline import CompanyHint, FounderHint, RawSignal
from app.sourcing.classify import classify_sector
from app.sourcing.client import fetch

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
# Split a "Show HN: <name> - <tagline>" title at the first separator.
_TITLE_SPLIT = re.compile(r"\s+[-–—/:]\s+|/")


def scan_hn(*, limit: int = 10, min_points: int = 15) -> list[RawSignal]:
    """Return up to ``limit`` Show HN launch signals, ranked by points velocity."""
    resp = fetch(
        _SEARCH_URL,
        params={
            "tags": "show_hn",
            "numericFilters": f"points>={min_points}",
            "hitsPerPage": min(limit * 3, 60),
        },
    )
    if resp.status_code != 200:
        return []

    hits = [h for h in resp.json().get("hits", []) if h.get("author") and h.get("title")]
    ranked = sorted(hits, key=_velocity, reverse=True)[:limit]
    return [_to_signal(h) for h in ranked]


def _age_days(hit: dict) -> float:
    created = hit.get("created_at_i")
    if not created:
        return 30.0
    return max((datetime.now(UTC).timestamp() - created) / 86400, 0.5)


def _velocity(hit: dict) -> float:
    return hit.get("points", 0) / _age_days(hit)


def _company_name(title: str) -> str:
    cleaned = re.sub(r"^\s*show hn:\s*", "", title, flags=re.IGNORECASE).strip()
    first = _TITLE_SPLIT.split(cleaned, maxsplit=1)[0].strip()
    return first or cleaned or title


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = url.split("//", 1)[-1].split("/", 1)[0].strip().lower()
    host = host.removeprefix("www.")
    return host or None


def _to_signal(hit: dict) -> RawSignal:
    title = hit["title"]
    author = hit["author"]
    url = hit.get("url")
    domain = _domain(url)
    story_id = hit["objectID"]
    content = {
        "kind": "show_hn",
        "title": title,
        "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
        "url": url,
        "linked_domain": domain,
        "points": hit.get("points", 0),
        "points_per_day": round(_velocity(hit), 1),
        "comments": hit.get("num_comments", 0),
        "author": author,
        "created": hit.get("created_at"),
        "story_id": story_id,
    }
    sector = classify_sector(title, domain)
    return RawSignal(
        source="hn",
        content=content,
        timestamp=datetime.fromtimestamp(hit["created_at_i"], tz=UTC)
        if hit.get("created_at_i")
        else datetime.now(UTC),
        dedup_key=f"hn:story:{story_id}",
        founder=FounderHint(
            name=author,
            links={"hn": f"https://news.ycombinator.com/user?id={author}"},
        ),
        company=CompanyHint(
            name=_company_name(title),
            domain=domain,
            sector=sector,
            stage="pre-seed",
            one_liner=title,
        ),
    )
