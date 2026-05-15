"""Alpha Vantage wrapper used as a fallback for fundamentals."""
from __future__ import annotations

import os
import httpx

BASE = "https://www.alphavantage.co/query"

def _key() -> str:
    k = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not k:
        raise RuntimeError("ALPHAVANTAGE_API_KEY not set")
    return k

def list_companies(country: str, limit: int) -> list[dict]:
    # Alpha Vantage has no per-country listing endpoint in the free tier.
    return []

def top_holders(ticker: str, limit: int = 10) -> list[dict]:
    return []  # not in free tier
