"""Thin HTTP helper shared by the live sourcing scanners.

Wraps ``httpx`` so every scanner reports failures the same way (``SourcingError``)
and the orchestrator can degrade one source without taking the whole scan down.
"""

from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = 20.0
USER_AGENT = "the-vc-brain-sourcing/0.1"


class SourcingError(RuntimeError):
    """A scanner could not complete: network, auth, or rate-limit failure."""


def fetch(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """GET ``url`` and return the response, mapping transport errors to ``SourcingError``.

    Status codes are intentionally left for the caller to interpret (e.g. GitHub
    signals rate limits via a 403 + ``X-RateLimit-Remaining`` header).
    """
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    try:
        return httpx.get(url, params=params, headers=merged, timeout=timeout)
    except httpx.HTTPError as exc:  # noqa: BLE001 - re-raised as a typed sourcing error
        raise SourcingError(f"request to {url} failed: {exc}") from exc
