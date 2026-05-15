"""Firecrawl URL-scraping wrapper.

Scrapes a URL and returns the markdown text.
Returns None (never raises) when FIRECRAWL_API_KEY is missing or the call fails.
"""
from __future__ import annotations

import logging
import os

import httpx

BASE = "https://api.firecrawl.dev/v1"
log = logging.getLogger(__name__)


def _key() -> str | None:
    return os.environ.get("FIRECRAWL_API_KEY") or None


def scrape(url: str) -> str | None:
    """Return scraped markdown for `url`. None when FIRECRAWL_API_KEY missing or error."""
    key = _key()
    if not key:
        log.warning("[firecrawl] FIRECRAWL_API_KEY not set — skipping scrape")
        return None
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{BASE}/scrape",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "formats": ["markdown"]},
            )
            if r.status_code != 200:
                log.warning("[firecrawl] scrape(%r) → HTTP %s", url, r.status_code)
                return None
            data = r.json()
        return data.get("data", {}).get("markdown") or None
    except Exception as exc:
        log.warning("[firecrawl] scrape(%r) failed: %s", url, exc)
        return None
