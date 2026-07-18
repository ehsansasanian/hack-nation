"""GitHub scanner: surface fast-rising, recently-created AI/infra repos.

Strategy: search recent repos with real star traction across a few AI/infra
topics, rank by *star velocity* (stars per day since creation), then enrich the
top candidates with owner profile, commit cadence, and README quality. Each
candidate becomes one ``RawSignal(source="github")`` whose ``dedup_key`` is the
repo's stable full name - so re-scans dedup cleanly even as the star count ticks
up (the pipeline just bumps ``last_seen``).

Auth: ``GITHUB_TOKEN`` if exported, otherwise the logged-in ``gh`` CLI token is
resolved at runtime (never written to disk here). Unauthenticated still works at
the lower 60 req/h limit; rate limits degrade gracefully via ``SourcingError``.
"""

from __future__ import annotations

import base64
import subprocess
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from app.config import GITHUB_TOKEN
from app.ingestion.pipeline import CompanyHint, FounderHint, RawSignal
from app.sourcing.classify import classify_sector
from app.sourcing.client import SourcingError, fetch

_SEARCH_URL = "https://api.github.com/search/repositories"
_API = "https://api.github.com"
_API_VERSION = "2022-11-28"

# A few AI/infra topics; each is one search call (search API is 30 req/min).
DEFAULT_TOPICS = ("llm", "ai-agents", "developer-tools", "inference")


@lru_cache(maxsize=1)
def _github_token() -> str | None:
    """Resolve a token: env var first, else the logged-in ``gh`` CLI token."""
    if GITHUB_TOKEN:
        return GITHUB_TOKEN
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip()
    return token or None


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": _API_VERSION}
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _check_rate_limit(resp) -> None:
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        reset = resp.headers.get("X-RateLimit-Reset", "?")
        raise SourcingError(f"GitHub rate limit exhausted (resets at epoch {reset}).")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _velocity(repo: dict) -> float:
    created = _parse_ts(repo["created_at"])
    age_days = max((datetime.now(UTC) - created).total_seconds() / 86400, 1.0)
    return repo.get("stargazers_count", 0) / age_days


def scan_github(
    *,
    limit: int = 10,
    min_stars: int = 250,
    days: int = 180,
    topics: tuple[str, ...] = DEFAULT_TOPICS,
    enrich: bool = True,
) -> list[RawSignal]:
    """Return up to ``limit`` GitHub repo signals, ranked by star velocity."""
    headers = _headers()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    ranked: dict[str, dict] = {}
    for topic in topics:
        query = f"topic:{topic} created:>{cutoff} stars:>{min_stars}"
        resp = fetch(
            _SEARCH_URL,
            params={"q": query, "sort": "stars", "order": "desc", "per_page": min(limit * 2, 40)},
            headers=headers,
        )
        _check_rate_limit(resp)
        if resp.status_code != 200:
            continue
        for repo in resp.json().get("items", []):
            ranked.setdefault(repo["full_name"], repo)

    top = sorted(ranked.values(), key=_velocity, reverse=True)[:limit]

    signals: list[RawSignal] = []
    for repo in top:
        content = _repo_content(repo)
        if enrich:
            _enrich(repo, content, headers)
        signals.append(_to_signal(repo, content))
    return signals


def _repo_content(repo: dict) -> dict:
    velocity = _velocity(repo)
    age_days = max(
        (datetime.now(UTC) - _parse_ts(repo["created_at"])).total_seconds() / 86400, 1.0
    )
    return {
        "kind": "repo",
        "repo": repo["full_name"],
        "url": repo["html_url"],
        "stars": repo.get("stargazers_count", 0),
        "stars_per_day": round(velocity, 1),
        "age_days": round(age_days),
        "created": repo["created_at"],
        "primary_language": repo.get("language"),
        "topics": repo.get("topics", []),
        "description": repo.get("description"),
        "open_issues": repo.get("open_issues_count"),
    }


def _enrich(repo: dict, content: dict, headers: dict) -> None:
    """Best-effort enrichment; any failed sub-call is skipped, not fatal."""
    full = repo["full_name"]
    owner_login = repo["owner"]["login"]
    content["owner_profile"] = _owner_profile(owner_login, headers)
    content["commit_cadence"] = _commit_cadence(full, headers)
    content["readme_quality"] = _readme_quality(full, headers)


def _owner_profile(login: str, headers: dict) -> dict:
    resp = fetch(f"{_API}/users/{login}", headers=headers)
    if resp.status_code != 200:
        return {"login": login}
    data = resp.json()
    return {
        "login": login,
        "name": data.get("name"),
        "bio": data.get("bio"),
        "company": data.get("company"),
        "location": data.get("location"),
        "followers": data.get("followers"),
        "public_repos": data.get("public_repos"),
        "created_at": data.get("created_at"),
        "blog": data.get("blog") or None,
    }


def _commit_cadence(full_name: str, headers: dict) -> dict:
    resp = fetch(f"{_API}/repos/{full_name}/commits", params={"per_page": 30}, headers=headers)
    if resp.status_code != 200:
        return {"sampled": 0}
    commits = resp.json()
    if not isinstance(commits, list) or not commits:
        return {"sampled": 0}
    dates = []
    for c in commits:
        stamp = (c.get("commit", {}).get("author") or {}).get("date")
        if stamp:
            dates.append(_parse_ts(stamp))
    if not dates:
        return {"sampled": len(commits)}
    span_days = max((max(dates) - min(dates)).total_seconds() / 86400, 0.5)
    return {
        "sampled": len(commits),
        "span_days": round(span_days, 1),
        "commits_per_day": round(len(dates) / span_days, 1),
        "last_commit": max(dates).date().isoformat(),
    }


def _readme_quality(full_name: str, headers: dict) -> dict:
    resp = fetch(f"{_API}/repos/{full_name}/readme", headers=headers)
    if resp.status_code != 200:
        return {"present": False}
    text = base64.b64decode(resp.json().get("content", "")).decode("utf-8", errors="ignore")
    lowered = text.lower()
    return {
        "present": True,
        "chars": len(text),
        "headings": text.count("\n#"),
        "has_code_block": "```" in text,
        "has_install": any(w in lowered for w in ("install", "getting started", "quickstart")),
    }


def _to_signal(repo: dict, content: dict) -> RawSignal:
    owner = repo["owner"]
    profile = content.get("owner_profile", {})
    domain = _homepage_domain(repo.get("homepage"))
    sector = classify_sector(
        " ".join(repo.get("topics", [])), repo.get("description"), repo["name"]
    )
    return RawSignal(
        source="github",
        content=content,
        timestamp=_parse_ts(repo["created_at"]),
        dedup_key=f"github:repo:{repo['full_name']}",
        founder=FounderHint(
            name=profile.get("name") or owner["login"],
            github_handle=owner["login"],
            links={"github": owner["html_url"], **({"blog": profile["blog"]} if profile.get("blog") else {})},
            bio=profile.get("bio"),
        ),
        company=CompanyHint(
            name=repo["name"],
            domain=domain,
            sector=sector,
            stage="pre-seed",  # a fresh, unfunded open-source project
            one_liner=repo.get("description"),
        ),
    )


def _homepage_domain(homepage: str | None) -> str | None:
    if not homepage:
        return None
    host = homepage.split("//", 1)[-1].split("/", 1)[0].strip().lower()
    host = host.removeprefix("www.")
    # Ignore non-product hosts that would collapse unrelated repos onto one company.
    if not host or any(h in host for h in ("github.com", "github.io", "gitlab.com")):
        return None
    return host
