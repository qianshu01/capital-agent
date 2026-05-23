"""Polygon ticker resolver. POLYGON_API_KEY env."""
from __future__ import annotations
import os
import httpx

BASE = "https://api.polygon.io"

def ticker_lookup(query: str, n: int = 5) -> list[dict]:
    """[{ticker, name, country}, ...]. [] on missing key/error."""
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        return []
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/v3/reference/tickers",
                      params={"search": query, "active": "true",
                              "limit": min(n, 10), "apiKey": key})
            if r.status_code != 200:
                return []
            data = r.json().get("results", [])
        return [{"ticker": t.get("ticker"), "name": t.get("name"),
                 "country": t.get("locale")} for t in data][:n]
    except Exception as e:
        print(f"[polygon] ticker_lookup({query}) failed: {e}")
        return []
