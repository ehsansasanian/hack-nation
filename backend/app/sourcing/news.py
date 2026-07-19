"""Startup-news scanner: free RSS/Atom feeds -> deterministic ``Signal(source="news")``.

Pulls recent items from a handful of free startup/venture news feeds (no key, no
license) and extracts, with pure string logic and $0 LLM:

* the article title, url, published date and a short excerpt;
* a conservative **company-name hint** from headline patterns ("X raises ...",
  "X launches ...") - only when the headline clearly leads with a named entity;
* **launch/funding keyword tags** and, when present, the funding amount.

Each item becomes one ``RawSignal(source="news")`` pushed through the *shared*
ingestion pipeline, so dedup + entity resolution are identical to every other
source. ``dedup_key`` is the immutable article guid (falling back to the url), so
re-scans never duplicate a story even as more feeds surface it.

Entity-resolution choice (conservative, honest):
    A news headline gives us a company *name* and sector but no identifiable,
    screenable founder. So when a confident "Company <funding/launch verb>"
    pattern yields a name we attach a ``CompanyHint`` - the pipeline then either
    exact-matches an existing company (a company already sourced from GitHub/HN
    now carries the news mention as corroborating evidence) or creates a
    lightweight company record. When no confident name is found we store the
    signal *unattached* (``company=None``), mirroring the arXiv scanner - the
    signal still enriches Memory but spawns nothing.

    News never attaches a founder and therefore never independently creates an
    outbound application: convergence in ``service.py`` requires a resolved
    founder, so a news-only company is ingest-only, while a news mention of a
    company that *does* have a founder converges through the exact same rules as
    every other source. This keeps us from fabricating a candidate out of a
    headline.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from app.ingestion.pipeline import CompanyHint, RawSignal
from app.sourcing.classify import classify_sector
from app.sourcing.client import SourcingError, fetch

# Free, reliable, no-key startup/venture news feeds (RSS 2.0).
FEEDS: tuple[tuple[str, str], ...] = (
    ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/"),
    ("TechCrunch Venture", "https://techcrunch.com/category/venture/feed/"),
    ("VentureBeat", "https://venturebeat.com/feed/"),
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_WS = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")

# Headline verbs that mark a fundraise or a product launch. Sentence-case feeds
# (TechCrunch / VentureBeat) keep these lowercase, so the company name is the
# Capitalized run that precedes them. Kept deliberately tight to stay conservative.
_FUNDING_VERBS = (
    "raises", "raised", "secures", "secured", "lands", "nabs", "bags", "snags",
    "scores", "closes", "banks", "grabs", "hauls in", "picks up", "pulls in",
)
_LAUNCH_VERBS = (
    "launches", "launched", "debuts", "unveils", "unveiled", "introduces",
    "rolls out", "ships", "emerges", "exits stealth",
)
_FUNDING_RE = "|".join(_FUNDING_VERBS)
_LAUNCH_RE = "|".join(_LAUNCH_VERBS)

# A company name: an uppercase-initial token run (allowing &, ., digits, hyphens)
# of up to four tokens. NOT case-insensitive on purpose - it must start uppercase.
_NAME = r"[A-Z][\w.&'’+-]*(?:\s+[A-Z0-9][\w.&'’+-]*){0,3}"

# Pattern A - the headline leads with the actor: "<Name> raises/launches ...".
_LEAD_RE = re.compile(rf"^(?P<name>{_NAME})\s+(?:{_FUNDING_RE}|{_LAUNCH_RE})\b")

# Pattern B - a fundraise stated mid-headline: "<Name> raises ... $" where the
# name sits immediately before the verb and a dollar amount follows in the same
# clause (the lookahead keeps precision high, e.g. "Neko Health raises $700M").
_FUND_RE = re.compile(rf"\b(?P<name>{_NAME})\s+(?:{_FUNDING_RE})\b(?=[^.]*\$)")

# Uppercase tokens that denote a role/label, not a company (guards Pattern B
# against "... VP raises $5M").
_ROLE_WORDS = {
    "vp", "ceo", "cto", "cfo", "coo", "exec", "president", "founder", "cofounder",
    "co", "boss", "chief", "head", "director", "lead", "svp", "evp",
}

# $5M / $5 million / $120M / $1.2B / $750K - deterministic amount capture.
_AMOUNT_RE = re.compile(
    r"\$\s?\d[\d.,]*\s?(?:b|bn|billion|m|mn|million|k|thousand)?", re.IGNORECASE
)

# Keyword tags scanned over title + excerpt (word-boundary, lowercased blob).
_TAG_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("funding", ("funding", "raises", "raised", "round", "investment", "backed", "capital")),
    ("seed", ("seed", "pre-seed", "angel")),
    ("series-a", ("series a",)),
    ("series-b", ("series b",)),
    ("series-c", ("series c", "series d", "series e")),
    ("valuation", ("valuation", "valued at", "unicorn")),
    ("launch", ("launch", "launches", "debut", "unveils", "rolls out", "introduces", "ships")),
    ("stealth", ("stealth",)),
    ("open-source", ("open source", "open-source")),
    ("acquisition", ("acquires", "acquired", "acquisition", "merger")),
)
_STAGE_BY_TAG = {"seed": "seed", "series-a": "series-a", "series-b": "series-b", "series-c": "series-c"}


def scan_news(*, limit: int = 10) -> list[RawSignal]:
    """Return up to ``limit`` recent startup-news signals, newest first.

    Each feed is fetched independently: a single failing feed is skipped, not
    fatal. Only if *every* feed is unreachable do we raise ``SourcingError`` so
    the orchestrator records it honestly in ``source_errors``.
    """
    signals: list[RawSignal] = []
    errors: list[str] = []
    responded = 0
    for name, url in FEEDS:
        try:
            resp = fetch(url, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        except SourcingError as exc:
            errors.append(f"{name}: {exc}")
            continue
        if resp.status_code != 200:
            errors.append(f"{name}: HTTP {resp.status_code}")
            continue
        responded += 1
        signals.extend(_parse_feed(resp.text, name))

    if responded == 0 and errors:
        raise SourcingError("no startup-news feed reachable: " + "; ".join(errors))

    # Newest first, then cap. Dedup across feeds is handled downstream by the
    # shared pipeline (stable guid/url dedup keys), so overlap is harmless.
    signals.sort(key=lambda s: s.timestamp, reverse=True)
    return signals[:limit]


def _parse_feed(text: str, feed_name: str) -> list[RawSignal]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    items = root.findall(".//item")  # RSS 2.0
    if items:
        return [s for it in items if (s := _rss_item(it, feed_name)) is not None]

    # Atom fallback (some feeds serve <feed><entry>...).
    entries = root.findall(f"{_ATOM}entry")
    return [s for e in entries if (s := _atom_entry(e, feed_name)) is not None]


def _clean(text: str | None) -> str:
    return _WS.sub(" ", _TAGS.sub(" ", text)).strip() if text else ""


def _rss_item(item: ET.Element, feed_name: str) -> RawSignal | None:
    title = _clean(item.findtext("title"))
    link = _clean(item.findtext("link"))
    if not title or not link:
        return None
    guid = _clean(item.findtext("guid")) or link
    published = _clean(item.findtext("pubDate"))
    excerpt = _clean(item.findtext("description"))[:280]
    return _build(feed_name, title, link, guid, published, excerpt)


def _atom_entry(entry: ET.Element, feed_name: str) -> RawSignal | None:
    title = _clean(_atom_text(entry, "title"))
    link_el = entry.find(f"{_ATOM}link")
    link = (link_el.get("href") if link_el is not None else "") or _clean(_atom_text(entry, "id"))
    if not title or not link:
        return None
    guid = _clean(_atom_text(entry, "id")) or link
    published = _clean(_atom_text(entry, "published") or _atom_text(entry, "updated"))
    excerpt = _clean(_atom_text(entry, "summary"))[:280]
    return _build(feed_name, title, link, guid, published, excerpt, atom=True)


def _atom_text(entry: ET.Element, tag: str) -> str | None:
    node = entry.find(f"{_ATOM}{tag}")
    return node.text if node is not None else None


def _build(
    feed_name: str,
    title: str,
    link: str,
    guid: str,
    published: str,
    excerpt: str,
    atom: bool = False,
) -> RawSignal:
    blob = f"{title} {excerpt}".lower()
    company = _company_name(title)
    tags = [tag for tag, kws in _TAG_KEYWORDS if any(k in blob for k in kws)]
    amount = _AMOUNT_RE.search(title)
    kind = "funding" if _has_funding(title, tags) else ("launch" if "launch" in tags else "news")
    sector = classify_sector(title, excerpt)
    stage = next((_STAGE_BY_TAG[t] for t in tags if t in _STAGE_BY_TAG), None)

    content = {
        "kind": kind,
        "title": title,
        "url": link,
        "guid": guid,
        "feed": feed_name,
        "published": published,
        "company_hint": company,
        "funding_amount": amount.group(0).strip() if amount else None,
        "sector_hint": sector,
        "tags": tags,
        "summary_excerpt": excerpt,
    }
    return RawSignal(
        source="news",
        content=content,
        timestamp=_parse_ts(published, atom),
        dedup_key=f"news:{guid}",
        founder=None,  # a headline names no screenable founder - never fabricate one
        company=(
            CompanyHint(name=company, sector=sector, stage=stage, one_liner=title)
            if company
            else None  # no confident company -> store the signal unattached (arXiv-style)
        ),
    )


def _company_name(title: str) -> str | None:
    """Extract a conservative company name from a "X raises/launches ..." headline.

    Two deterministic patterns: the actor leading the headline, or a fundraise
    named mid-headline with a dollar amount. Returns None when neither fires - the
    honest signal that we could not confidently name a company.
    """
    match = _LEAD_RE.match(title) or _FUND_RE.search(title)
    if not match:
        return None
    name = match.group("name").strip(" -–—")
    if not (2 <= len(name) <= 48):
        return None
    if name.lower() in _NON_COMPANY_LEADS:
        return None
    tokens = name.split()
    if tokens[-1].lower() in _ROLE_WORDS:  # "... hardware VP" -> not a company
        return None
    if name.isupper() and len(name) <= 4:  # bare acronym (AI / IPO / GPT)
        return None
    return name


# Capitalized headline leads that are not company names.
_NON_COMPANY_LEADS = {
    "report", "exclusive", "startup", "startups", "the", "this", "these", "new",
    "why", "how", "what", "meet", "watch", "opinion", "analysis", "breaking",
}


def _has_funding(title: str, tags: list[str]) -> bool:
    lower = title.lower()
    return any(v in lower for v in _FUNDING_VERBS) or "funding" in tags


def _parse_ts(value: str, atom: bool) -> datetime:
    if not value:
        return datetime.now(UTC)
    if atom:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
    try:
        dt = parsedate_to_datetime(value)  # RFC 822 (RSS pubDate)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)
