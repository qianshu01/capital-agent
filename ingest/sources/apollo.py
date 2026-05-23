"""Apollo organization lookup. APOLLO_API_KEY env."""
from __future__ import annotations
import os
import httpx

URL = "https://api.apollo.io/v1/organizations/search"

def org_lookup(name: str) -> dict | None:
    """{website, hq_country, employees, founded_year, industry}. None on miss."""
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        return None
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(URL, headers={"X-Api-Key": key, "Content-Type": "application/json"},
                       json={"q_organization_name": name, "page": 1, "per_page": 1})
            if r.status_code != 200:
                print(f"[apollo] {r.status_code}: {r.text[:200]}")
                return None
            orgs = r.json().get("organizations", [])
        if not orgs:
            return None
        o = orgs[0]
        return {
            "website": o.get("website_url"),
            "hq_country": o.get("country"),
            "employees": o.get("estimated_num_employees"),
            "founded_year": o.get("founded_year"),
            "industry": o.get("industry"),
        }
    except Exception as e:
        print(f"[apollo] failed for {name}: {e}")
        return None
