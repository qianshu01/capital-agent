"""Finnhub fundamentals lookup. FINNHUB_API_KEY env."""
from __future__ import annotations
import os
import httpx

BASE = "https://finnhub.io/api/v1"

def company(ticker: str) -> dict | None:
    """{market_cap, name, exchange, industry}. None on missing key/miss."""
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/stock/profile2",
                      params={"symbol": ticker, "token": key})
            if r.status_code != 200 or not r.json():
                return None
            p = r.json()
        return {
            "market_cap": (p.get("marketCapitalization") or 0) * 1_000_000,
            "name": p.get("name"),
            "exchange": p.get("exchange"),
            "industry": p.get("finnhubIndustry"),
        }
    except Exception as e:
        print(f"[finnhub] company({ticker}) failed: {e}")
        return None
