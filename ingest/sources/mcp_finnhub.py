"""Finnhub MCP wrapper."""
from __future__ import annotations

import os
import httpx

BASE = "https://finnhub.io/api/v1"

def _key() -> str:
    k = os.environ.get("FINNHUB_API_KEY")
    if not k:
        raise RuntimeError("FINNHUB_API_KEY not set")
    return k

# Finnhub uses exchange codes (e.g. HK, T, KS, SI) rather than country codes.
EXCHANGE_BY_COUNTRY = {
    "HK": "HK", "JP": "T", "KR": "KS", "SG": "SI",
    "IN": "BO", "AU": "AX", "CN": "SS",
    "MY": "KL", "ID": "JK", "TH": "BK", "PH": "PS", "NZ": "NZ", "VN": "HM",
}

def list_companies(country: str, limit: int) -> list[dict]:
    code = EXCHANGE_BY_COUNTRY.get(country.upper())
    if not code:
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{BASE}/stock/symbol",
                params={"exchange": code, "token": _key()},
            )
            r.raise_for_status()
            symbols = r.json()
        out: list[dict] = []
        for s in symbols[:limit]:
            tkr = s.get("symbol")
            try:
                p = client.get(
                    f"{BASE}/stock/profile2",
                    params={"symbol": tkr, "token": _key()},
                    timeout=10.0,
                )
                prof = p.json() if p.status_code == 200 else {}
            except Exception:
                prof = {}
            out.append({
                "ticker": tkr,
                "name": prof.get("name") or s.get("description"),
                "exchange": code,
                "market_cap": (prof.get("marketCapitalization") or 0) * 1_000_000,
                "industry": prof.get("finnhubIndustry"),
            })
        return out
    except Exception as e:
        print(f"[finnhub] list_companies({country}) failed: {e}")
        return []

def top_holders(ticker: str, limit: int = 10) -> list[dict]:
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{BASE}/stock/ownership",
                params={"symbol": ticker, "limit": limit, "token": _key()},
            )
            if r.status_code != 200:
                return []
            data = r.json().get("ownership", [])
        return [{"name": h.get("name"), "share": h.get("share"),
                 "pct": h.get("percent")} for h in data][:limit]
    except Exception as e:
        print(f"[finnhub] top_holders({ticker}) failed: {e}")
        return []
