"""arXiv scanner: recent cs.AI papers, lead-author extraction (optional 3rd source).

Papers are not companies, so an arXiv find never becomes an application - it
attaches a research signal to the lead author (a founder node), enriching the
founder graph and proving the pipeline ingests a heterogeneous third source.
``dedup_key`` is the stable arXiv id, so re-scans never duplicate a paper.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from app.ingestion.pipeline import FounderHint, RawSignal
from app.sourcing.client import fetch

_QUERY_URL = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"
_WS = re.compile(r"\s+")


def scan_arxiv(*, limit: int = 10, category: str = "cs.AI") -> list[RawSignal]:
    """Return up to ``limit`` recent papers from ``category`` as author signals."""
    resp = fetch(
        _QUERY_URL,
        params={
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": limit,
        },
        headers={"Accept": "application/atom+xml"},
    )
    if resp.status_code != 200:
        return []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []

    signals: list[RawSignal] = []
    for entry in root.findall(f"{_ATOM}entry"):
        signal = _to_signal(entry, category)
        if signal is not None:
            signals.append(signal)
    return signals


def _text(node: ET.Element | None) -> str:
    return _WS.sub(" ", node.text).strip() if node is not None and node.text else ""


def _to_signal(entry: ET.Element, category: str) -> RawSignal | None:
    id_url = _text(entry.find(f"{_ATOM}id"))
    authors = [_text(a.find(f"{_ATOM}name")) for a in entry.findall(f"{_ATOM}author")]
    authors = [a for a in authors if a]
    if not id_url or not authors:
        return None

    arxiv_id = id_url.rstrip("/").split("/")[-1]
    published = _text(entry.find(f"{_ATOM}published"))
    content = {
        "kind": "paper",
        "title": _text(entry.find(f"{_ATOM}title")),
        "arxiv_id": arxiv_id,
        "url": id_url,
        "published": published,
        "primary_category": category,
        "authors": authors,
        "num_authors": len(authors),
        "summary_excerpt": _text(entry.find(f"{_ATOM}summary"))[:280],
    }
    return RawSignal(
        source="arxiv",
        content=content,
        timestamp=_parse_ts(published),
        dedup_key=f"arxiv:{arxiv_id}",
        founder=FounderHint(
            name=authors[0],  # lead author becomes the founder node
            links={"arxiv": id_url},
            bio=f"Lead author on arXiv {category} preprint.",
        ),
        company=None,  # a paper is not a company - no application is created
    )


def _parse_ts(value: str) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
