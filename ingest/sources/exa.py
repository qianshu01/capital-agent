"""Exa neural web-search wrapper.

Uses the Exa search API to find candidate family-office and holding-company pages.
Returns empty results (never raises) when EXA_API_KEY is missing or the call fails.
"""
from __future__ import annotations

import logging
import os

import httpx

BASE = "https://api.exa.ai"
log = logging.getLogger(__name__)


def _key() -> str | None:
    return os.environ.get("EXA_API_KEY") or None


def search(query: str, n: int = 10) -> list[dict]:
    """Return [{url, title, snippet}] for `query`. [] when EXA_API_KEY missing."""
    key = _key()
    if not key:
        log.warning("[exa] EXA_API_KEY not set — skipping search")
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{BASE}/search",
                headers={"x-api-key": key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": n,
                    "contents": {"text": {"maxCharacters": 400}},
                },
            )
            if r.status_code != 200:
                log.warning("[exa] search(%r) → HTTP %s", query, r.status_code)
                return []
            results = r.json().get("results", [])
        return [
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": (item.get("text") or item.get("snippet") or "")[:400],
            }
            for item in results
        ]
    except Exception as exc:
        log.warning("[exa] search(%r) failed: %s", query, exc)
        return []
