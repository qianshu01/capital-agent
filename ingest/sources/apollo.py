"""Apollo.io organization and contact lookup wrapper.

Uses the Apollo API to enrich organization details and find key contacts.
Returns None / [] (never raises) when APOLLO_API_KEY is missing or the call fails.
"""
from __future__ import annotations

import logging
import os

import httpx

BASE = "https://api.apollo.io/v1"
log = logging.getLogger(__name__)


def _key() -> str | None:
    return os.environ.get("APOLLO_API_KEY") or None


def org_lookup(name: str) -> dict | None:
    """Return {name, website, employees, founded_year, industry}. None on miss."""
    key = _key()
    if not key:
        log.warning("[apollo] APOLLO_API_KEY not set — skipping org_lookup")
        return None
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{BASE}/organizations/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": key,
                },
                json={"q_organization_name": name, "page": 1, "per_page": 1},
            )
            if r.status_code != 200:
                log.warning("[apollo] org_lookup(%r) → HTTP %s", name, r.status_code)
                return None
            orgs = r.json().get("organizations", [])
            if not orgs:
                return None
            org = orgs[0]

        return {
            "name": org.get("name"),
            "website": org.get("website_url"),
            "employees": org.get("estimated_num_employees"),
            "founded_year": org.get("founded_year"),
            "industry": org.get("industry"),
        }
    except Exception as exc:
        log.warning("[apollo] org_lookup(%r) failed: %s", name, exc)
        return None


def key_contacts(org_name: str, limit: int = 5) -> list[dict]:
    """Return [{name, title, linkedin_url}] without leaking emails. [] on miss."""
    key = _key()
    if not key:
        log.warning("[apollo] APOLLO_API_KEY not set — skipping key_contacts")
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{BASE}/people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": key,
                },
                json={
                    "q_organization_name": org_name,
                    "person_titles": [
                        "Chief Investment Officer", "Managing Director",
                        "Partner", "Principal", "Portfolio Manager",
                        "Head of Investments", "Family Office Director",
                    ],
                    "page": 1,
                    "per_page": limit,
                },
            )
            if r.status_code != 200:
                log.warning("[apollo] key_contacts(%r) → HTTP %s", org_name, r.status_code)
                return []
            people = r.json().get("people", [])

        return [
            {
                "name": p.get("name", ""),
                "title": p.get("title", ""),
                "linkedin_url": p.get("linkedin_url", ""),
            }
            for p in people
        ]
    except Exception as exc:
        log.warning("[apollo] key_contacts(%r) failed: %s", org_name, exc)
        return []
