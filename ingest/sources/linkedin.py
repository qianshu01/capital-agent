"""LinkedIn data wrapper via Proxycurl API.

Uses the Proxycurl API (https://nubela.co/proxycurl) to fetch person and company profiles.
Returns None (never raises) when LINKEDIN_API_KEY is missing or the call fails.
"""
from __future__ import annotations

import logging
import os

import httpx

BASE = "https://nubela.co/proxycurl/api/v2"
log = logging.getLogger(__name__)


def _key() -> str | None:
    return os.environ.get("LINKEDIN_API_KEY") or None


def person_profile(linkedin_url: str) -> dict | None:
    """Return {full_name, headline, current_role, summary}. None on miss."""
    key = _key()
    if not key:
        log.warning("[linkedin] LINKEDIN_API_KEY not set — skipping person_profile")
        return None
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{BASE}/linkedin",
                headers={"Authorization": f"Bearer {key}"},
                params={"url": linkedin_url, "use_cache": "if-present"},
            )
            if r.status_code != 200:
                log.warning("[linkedin] person_profile(%r) → HTTP %s", linkedin_url, r.status_code)
                return None
            data = r.json()

        # Derive current_role from most recent experience entry
        experiences = data.get("experiences") or []
        current_role = None
        if experiences:
            exp = experiences[0]
            title = exp.get("title", "")
            company = exp.get("company", "")
            current_role = f"{title} at {company}" if title and company else title or company or None

        return {
            "full_name": data.get("full_name"),
            "headline": data.get("headline"),
            "current_role": current_role,
            "summary": data.get("summary"),
        }
    except Exception as exc:
        log.warning("[linkedin] person_profile(%r) failed: %s", linkedin_url, exc)
        return None


def company_profile(linkedin_url: str) -> dict | None:
    """Return {name, industry, employee_count, headquarter_country}. None on miss."""
    key = _key()
    if not key:
        log.warning("[linkedin] LINKEDIN_API_KEY not set — skipping company_profile")
        return None
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{BASE}/linkedin/company",
                headers={"Authorization": f"Bearer {key}"},
                params={"url": linkedin_url, "use_cache": "if-present"},
            )
            if r.status_code != 200:
                log.warning("[linkedin] company_profile(%r) → HTTP %s", linkedin_url, r.status_code)
                return None
            data = r.json()

        hq = data.get("hq") or {}
        return {
            "name": data.get("name"),
            "industry": data.get("industry"),
            "employee_count": data.get("company_size_on_linkedin"),
            "headquarter_country": hq.get("country"),
        }
    except Exception as exc:
        log.warning("[linkedin] company_profile(%r) failed: %s", linkedin_url, exc)
        return None
