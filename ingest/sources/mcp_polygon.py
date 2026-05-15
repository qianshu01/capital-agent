"""Polygon.io MCP wrapper. Reads POLYGON_API_KEY from env."""
from __future__ import annotations

import os
import httpx

BASE = "https://api.polygon.io"

def _key() -> str:
    k = os.environ.get("POLYGON_API_KEY")
    if not k:
        raise RuntimeError("POLYGON_API_KEY not set")
    return k

def list_companies(country: str, limit: int) -> list[dict]:
    """Return [{ticker, name, exchange, market_cap, industry}, ...] for `country`.
    Polygon's reference endpoint covers US-listed primarily; for HK/SG/JP/etc.
    fall back to empty list and let other MCP sources cover the gap.
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{BASE}/v3/reference/tickers",
                params={"market": "stocks", "active": "true",
                        "limit": min(limit, 1000), "apiKey": _key()},
            )
            r.raise_for_status()
            data = r.json().get("results", [])
        return [
            {"ticker": t["ticker"], "name": t.get("name"),
             "exchange": t.get("primary_exchange"),
             "market_cap": t.get("market_cap"),
             "industry": t.get("sic_description")}
            for t in data
            if (t.get("locale") or "").upper() == country.upper()
        ][:limit]
    except Exception as e:
        print(f"[polygon] list_companies({country}) failed: {e}")
        return []

def top_holders(ticker: str, limit: int = 10) -> list[dict]:
    # Polygon does not expose holder lists in the free tier; return empty.
    return []
