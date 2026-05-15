"""Pure rule-based classification helpers. No I/O."""
from __future__ import annotations

import re

CORPORATE_PATTERN = re.compile(
    r"\b(Inc|Corp|Corporation|Ltd|Limited|Pte|Plc|GmbH|Trust\s+Co|Bank|Fund|"
    r"ETF|Pension|Sovereign|Capital|Asset\s+Mgmt|Asset\s+Management|"
    r"Securities|Holdings|Investments\s+Inc)\b",
    re.IGNORECASE,
)

REGION_BY_COUNTRY = {
    # East Asia
    "CN": "East Asia", "HK": "East Asia", "JP": "East Asia",
    "KR": "East Asia", "MN": "East Asia",
    # SEA
    "SG": "SEA", "MY": "SEA", "ID": "SEA", "TH": "SEA", "PH": "SEA",
    "VN": "SEA", "KH": "SEA", "LA": "SEA", "MM": "SEA", "BN": "SEA",
    # South Asia
    "IN": "South Asia", "PK": "South Asia", "LK": "South Asia",
    "BD": "South Asia", "NP": "South Asia", "BT": "South Asia",
    # Oceania
    "AU": "Oceania", "NZ": "Oceania",
    # Central Asia
    "KZ": "Central Asia",
}

def region_for_country(code: str) -> str:
    return REGION_BY_COUNTRY.get(code.upper(), "Unknown")

def is_family_holder(
    name: str,
    *,
    country: str | None = None,
    known: dict[str, list[str]] | None = None,
) -> bool:
    """Return True if the holder name looks like an individual or known family."""
    if not name:
        return False
    if known and country and country.upper() in known:
        for fam in known[country.upper()]:
            if fam.lower() in name.lower():
                return True
    if CORPORATE_PATTERN.search(name):
        return False
    # Heuristic: 2+ alphabetic tokens, no digits → likely a personal name
    tokens = [t for t in re.split(r"[\s.\-]+", t) if t] if False else [t for t in re.split(r"[\s.\-]+", name) if t]
    if len(tokens) >= 2 and all(re.match(r"^[A-Za-z'\-]+$", t) for t in tokens):
        return True
    return False

def infer_data_quality(
    *,
    aum_basis: str | None,
    controllers: list[str] | None,
    recent_activity_count: int,
) -> int:
    has_controllers = bool(controllers)
    has_activity = recent_activity_count > 0
    if aum_basis == "disclosed" and has_controllers and has_activity:
        return 5
    if aum_basis == "market_cap" and has_controllers and has_activity:
        return 4
    if aum_basis in ("market_cap", "estimate") and (has_controllers or has_activity):
        return 3
    if aum_basis == "estimate":
        return 2
    return 1
