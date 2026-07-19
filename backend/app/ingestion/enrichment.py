"""Inbound enrichment: fetch self-declared founder links, feed them as evidence.

This is the ``enriching`` stage of the auto-analysis chain (it runs BEFORE
screening). For every link a founder declared on apply it attempts a retrieval and
routes the result through the *shared* ingestion pipeline, so enrichment signals
are source-tagged, timestamped, deduplicated and entity-resolved onto the founder
exactly like any other signal - and then flow into scoring, diligence, the memo
and the trace with no special-casing downstream.

Retrieval per source:

* GitHub  - REST profile + top repos (reuses ``sourcing/github.enrich_github_handle``).
* Website - HTTP fetch -> LLM extraction into structured facts (gpt-4o-mini); the
  offline path stores a cleaned text excerpt as a signal, no LLM call.
* LinkedIn / X - attempted public fetch; these are typically auth-walled, so the
  expected outcome is ``blocked`` and we record a self-declared *reference* signal.
  Content is NEVER fabricated - a source becomes evidence only if actually fetched.

Every source records an outcome (``fetched`` / ``blocked`` / ``error``); a fetch
failure is caught and reported, it never fails the analysis chain. The per-source
report (``source -> {outcome, signal_count}``) is persisted on
``Application.enrichment_report`` for the API/UI to render.
"""

from __future__ import annotations

import html
import os
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import OPENAI_API_KEY
from app.ingestion.pipeline import FounderHint, RawSignal, ingest_signal
from app.models import Application, Company
from app.sourcing.client import SourcingError, fetch
from app.sourcing.github import enrich_github_handle, normalize_github_handle

# Signal source tags for enrichment (github reuses the existing tag).
WEB_SOURCE = "web"
LINKEDIN_SOURCE = "linkedin"
X_SOURCE = "x"

_WEB_MODEL = "gpt-4o-mini"
_MAX_WEBSITE_CHARS = 6000  # cap the text handed to the extractor / stored excerpt
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _llm_enabled(prefer: str | None) -> bool:
    """Mirror ``reasoning.backend.get_backend`` so enrichment obeys the same switch."""
    mode = (prefer or os.getenv("VC_BRAIN_LLM", "auto")).strip().lower()
    if mode == "offline":
        return False
    if mode == "openai":
        return True
    return bool(OPENAI_API_KEY)  # auto


# --- link normalisation ------------------------------------------------------


def _clean_url(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    if not v.startswith(("http://", "https://")):
        v = "https://" + v
    return v


def _records(app: Application) -> list[dict]:
    """Founder link records to enrich, from declared_links with a founder fallback."""
    records = list(app.declared_links or [])
    if records:
        return records
    # No explicit declared_links: fall back to founders that carry links/handles,
    # so an inbound app whose founder already has a github handle still enriches.
    fallback: list[dict] = []
    for f in app.company.founders:
        links = f.links or {}
        rec = {
            "name": f.name,
            "github": f.github_handle or links.get("github"),
            "linkedin": links.get("linkedin"),
            "website": links.get("website") or links.get("blog"),
            "x": links.get("x") or links.get("twitter"),
        }
        if any(rec[k] for k in ("github", "linkedin", "website", "x")):
            fallback.append(rec)
    return fallback


# --- website extraction ------------------------------------------------------


def _html_to_text(body: str) -> str:
    body = _SCRIPT_STYLE_RE.sub(" ", body)
    body = _TAG_RE.sub(" ", body)
    body = html.unescape(body)
    return _WS_RE.sub(" ", body).strip()


def _fetch_website_text(url: str) -> str:
    resp = fetch(url, headers={"Accept": "text/html,application/xhtml+xml"})
    if resp.status_code != 200:
        raise SourcingError(f"website fetch returned HTTP {resp.status_code}")
    text = _html_to_text(resp.text)
    if not text:
        raise SourcingError("website returned no readable text")
    return text[:_MAX_WEBSITE_CHARS]


def _extract_website_facts_llm(url: str, text: str) -> dict:
    """Structured extraction from real fetched text - never invents content."""
    from pydantic import BaseModel
    from openai import OpenAI

    from app.reasoning.openai_backend import USAGE

    class WebsiteFacts(BaseModel):
        role: str = ""
        background: str = ""
        product_claims: list[str] = []
        traction_mentions: list[str] = []
        summary: str = ""

    client = OpenAI(api_key=OPENAI_API_KEY)
    user = (
        f"Personal/company website: {url}\n\n"
        f"PAGE TEXT (verbatim, may be truncated):\n{text}\n\n"
        "Extract ONLY facts present in the text about the founder/company: their role, "
        "background, concrete product claims, and any traction/revenue/customer mentions. "
        "Do NOT infer or invent anything not stated. Leave a field empty if the text does "
        "not state it. Keep each item short."
    )
    completion = client.beta.chat.completions.parse(
        model=_WEB_MODEL,
        messages=[
            {"role": "system", "content": "You extract structured facts from web page text. You never invent facts not present in the text."},
            {"role": "user", "content": user},
        ],
        response_format=WebsiteFacts,
        temperature=0.1,
    )
    if completion.usage is not None:
        USAGE.add(_WEB_MODEL, completion.usage.prompt_tokens, completion.usage.completion_tokens)
    facts = completion.choices[0].message.parsed
    return facts.model_dump() if facts is not None else {}


def _website_signal(url: str, hint: FounderHint, prefer: str | None) -> RawSignal:
    text = _fetch_website_text(url)
    content: dict = {"kind": "website", "url": url, "fetch_outcome": "fetched", "self_declared": True}
    if _llm_enabled(prefer):
        content["extraction"] = "llm"
        content.update(_extract_website_facts_llm(url, text))
    else:
        # Offline fallback: store a cleaned text excerpt as the signal, no LLM.
        content["extraction"] = "text-excerpt"
        content["excerpt"] = text[:1500]
    return RawSignal(
        source=WEB_SOURCE,
        content=content,
        timestamp=datetime.now(UTC),
        dedup_key=f"web:{url}",
        founder=hint,
        company=None,
    )


def _blocked_reference_signal(url: str, source: str, hint: FounderHint) -> RawSignal:
    """A self-declared reference for an auth-walled source - content, never fabricated."""
    label = {LINKEDIN_SOURCE: "LinkedIn", X_SOURCE: "X"}.get(source, source)
    return RawSignal(
        source=source,
        content={
            "kind": "self_declared_reference",
            "url": url,
            "fetch_outcome": "blocked",
            "note": f"{label} profile is self-declared but auth-walled; recorded as a reference only, no content fetched.",
            "self_declared": True,
        },
        timestamp=datetime.now(UTC),
        dedup_key=f"{source}:{url}",
        founder=hint,
        company=None,
    )


# --- report ------------------------------------------------------------------


_OUTCOME_RANK = {"error": 0, "blocked": 1, "fetched": 2}


def _record_outcome(report: dict, source: str, outcome: str, n: int, note: str | None = None) -> None:
    entry = report.setdefault(source, {"outcome": outcome, "signal_count": 0})
    entry["signal_count"] += n
    # Best outcome across founders wins as the headline (fetched > blocked > error).
    if _OUTCOME_RANK.get(outcome, 0) >= _OUTCOME_RANK.get(entry["outcome"], 0):
        entry["outcome"] = outcome
    if note and "note" not in entry:
        entry["note"] = note


# --- orchestration -----------------------------------------------------------


def _hint_for(record: dict, fallback_name: str | None) -> FounderHint:
    # Enrichment runs before scoring and is what first resolves/creates each declared
    # co-founder (via their GitHub signal), so it must carry the declared bio - else a
    # new co-founder is created bio-less and team-complementarity can never read them.
    from app.reasoning.context import _bio_from_record

    name = record.get("name") or fallback_name
    gh = normalize_github_handle(record.get("github"))
    return FounderHint(name=name, github_handle=gh, bio=_bio_from_record(record))


def _ingest(session: Session, signals: list[RawSignal]) -> int:
    """Ingest a batch, returning how many signals were recorded (created + deduped)."""
    n = 0
    for raw in signals:
        signal, _created = ingest_signal(session, raw)
        if signal is not None:
            n += 1
    return n


def enrich_application(
    session: Session, application_id: int, prefer_backend: str | None = None
) -> dict:
    """Fetch every declared link for one application and record a per-source report.

    Returns the report and persists it on ``Application.enrichment_report``. Never
    raises: any per-source failure is caught and recorded as an ``error`` outcome so
    the analysis chain always proceeds to screening.
    """
    app = session.get(Application, application_id)
    if app is None:
        raise LookupError(f"Application {application_id} not found.")
    # company.founders needed for the fallback + a single-founder default name.
    company = session.get(Company, app.company_id)
    fallback_name = (
        company.founders[0].name if company and len(company.founders) == 1 else None
    )

    report: dict = {}
    for record in _records(app):
        hint = _hint_for(record, fallback_name)

        gh = record.get("github")
        if gh:
            try:
                signals = enrich_github_handle(gh, founder_name=hint.name)
                n = _ingest(session, signals)
                _record_outcome(report, "github", "fetched", n)
            except Exception as exc:  # noqa: BLE001 - never fail the chain
                _record_outcome(report, "github", "error", 0, note=str(exc)[:200])

        website = _clean_url(record.get("website"))
        if website:
            try:
                n = _ingest(session, [_website_signal(website, hint, prefer_backend)])
                _record_outcome(report, WEB_SOURCE, "fetched", n)
            except Exception as exc:  # noqa: BLE001
                _record_outcome(report, WEB_SOURCE, "error", 0, note=str(exc)[:200])

        linkedin = _clean_url(record.get("linkedin"))
        if linkedin:
            n = _ingest(session, [_blocked_reference_signal(linkedin, LINKEDIN_SOURCE, hint)])
            _record_outcome(
                report, LINKEDIN_SOURCE, "blocked", n,
                note="auth-walled; stored as self-declared reference",
            )

        x_link = _clean_url(record.get("x"))
        if x_link:
            n = _ingest(session, [_blocked_reference_signal(x_link, X_SOURCE, hint)])
            _record_outcome(
                report, X_SOURCE, "blocked", n,
                note="auth-walled; stored as self-declared reference",
            )

    app.enrichment_report = report
    session.commit()
    return report
