"""Firecrawl URL → markdown wrapper. FIRECRAWL_API_KEY env."""
from __future__ import annotations
import os
import httpx

URL = "https://api.firecrawl.dev/v1/scrape"
MAX_CHARS = 8000

def scrape(url: str) -> str | None:
    """Markdown text of `url` (truncated to MAX_CHARS). None on missing key/error."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        with httpx.Client(timeout=45.0) as c:
            r = c.post(URL, headers={"Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json"},
                       json={"url": url, "formats": ["markdown"]})
            if r.status_code != 200:
                print(f"[firecrawl] {r.status_code} for {url}: {r.text[:200]}")
                return None
            md = (r.json().get("data") or {}).get("markdown")
        return (md or "")[:MAX_CHARS] or None
    except Exception as e:
        print(f"[firecrawl] failed for {url}: {e}")
        return None
