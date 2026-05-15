"""Crunchbase organization lookup wrapper.

Uses the Crunchbase API v4 to look up organizations and recent deals.
Returns None / [] (never raises) when CRUNCHBASE_API_KEY is missing or the call fails.
"""
from __future__ import annotations

import logging
import os

import httpx

BASE = "https://api.crunchbase.com/api/v4"
log = logging.getLogger(__name__)


def _key() -> str | None:
    return os.environ.get("CRUNCHBASE_API_KEY") or None


def find_org(name: str) -> dict | None:
    """Return {uuid, name, short_description, last_funding_at, total_funding_usd, founders}. None on miss."""
    key = _key()
    if not key:
        log.warning("[crunchbase] CRUNCHBASE_API_KEY not set — skipping find_org")
        return None
    try:
        with httpx.Client(timeout=30.0) as client:
            # Use the Crunchbase autocomplete endpoint to find the org permalink
            r = client.get(
                f"{BASE}/autocompletes",
                params={"query": name, "collection_ids": "organizations", "user_key": key},
            )
            if r.status_code != 200:
                log.warning("[crunchbase] find_org(%r) autocomplete → HTTP %s", name, r.status_code)
                return None
            entities = r.json().get("entities", [])
            if not entities:
                return None
            permalink = entities[0].get("identifier", {}).get("permalink")
            if not permalink:
                return None

            # Fetch org details
            r2 = client.get(
                f"{BASE}/entities/organizations/{permalink}",
                params={
                    "user_key": key,
                    "field_ids": (
                        "uuid,name,short_description,"
                        "last_funding_at,total_funding_usd,"
                        "founder_identifiers"
                    ),
                },
            )
            if r2.status_code != 200:
                log.warning("[crunchbase] find_org(%r) detail → HTTP %s", name, r2.status_code)
                return None
            props = r2.json().get("properties", {})

        founders = [
            f.get("value", "")
            for f in (props.get("founder_identifiers") or [])
        ]
        return {
            "uuid": props.get("uuid"),
            "name": props.get("name"),
            "short_description": props.get("short_description"),
            "last_funding_at": props.get("last_funding_at"),
            "total_funding_usd": props.get("total_funding_usd"),
            "founders": founders,
        }
    except Exception as exc:
        log.warning("[crunchbase] find_org(%r) failed: %s", name, exc)
        return None


def recent_deals(org_name: str, limit: int = 5) -> list[dict]:
    """Return [{date, kind, description, source_url}]. [] on miss."""
    key = _key()
    if not key:
        log.warning("[crunchbase] CRUNCHBASE_API_KEY not set — skipping recent_deals")
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            # Find org permalink first
            r = client.get(
                f"{BASE}/autocompletes",
                params={"query": org_name, "collection_ids": "organizations", "user_key": key},
            )
            if r.status_code != 200:
                log.warning("[crunchbase] recent_deals(%r) autocomplete → HTTP %s", org_name, r.status_code)
                return []
            entities = r.json().get("entities", [])
            if not entities:
                return []
            permalink = entities[0].get("identifier", {}).get("permalink")
            if not permalink:
                return []

            # Search investments/funding rounds for this org
            r2 = client.post(
                f"{BASE}/searches/funding_rounds",
                params={"user_key": key},
                json={
                    "field_ids": ["announced_on", "investment_type", "short_description", "lead_investor_identifiers"],
                    "query": [
                        {
                            "type": "predicate",
                            "field_id": "funded_organization_identifier",
                            "operator_id": "includes",
                            "values": [permalink],
                        }
                    ],
                    "order": [{"field_id": "announced_on", "sort": "desc"}],
                    "limit": limit,
                },
            )
            if r2.status_code != 200:
                log.warning("[crunchbase] recent_deals(%r) search → HTTP %s", org_name, r2.status_code)
                return []
            rounds = r2.json().get("entities", [])

        out = []
        for rnd in rounds:
            props = rnd.get("properties", {})
            out.append({
                "date": props.get("announced_on"),
                "kind": props.get("investment_type", "deal"),
                "description": props.get("short_description") or props.get("investment_type", ""),
                "source_url": f"https://www.crunchbase.com/organization/{permalink}",
            })
        return out
    except Exception as exc:
        log.warning("[crunchbase] recent_deals(%r) failed: %s", org_name, exc)
        return []
