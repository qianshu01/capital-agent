"""Ingestion orchestrator. Idempotent given fixed inputs.

Usage:
  python -m ingest.run --out data/capital.db [--enrich] [--discover] [--enrich-sources] [--config ingest/config.yaml]

Flags:
  --enrich          LLM enrichment via OpenRouter (adds thesis_blurb, fills soft fields).
  --discover        Exa discovery pass — logs candidate URLs to data/discovery_candidates.json.
  --enrich-sources  Per-source enrichment pass (Crunchbase, Apollo, LinkedIn, Firecrawl).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional at runtime; warn below if needed

from ingest import write_db
from ingest.classify import (
    is_family_holder, region_for_country, infer_data_quality,
)
from ingest.enrich_llm import enrich
from ingest.sources import exa, firecrawl, crunchbase, apollo

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

NOW = dt.datetime.utcnow().isoformat() + "Z"


def _slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


# ---------------------------------------------------------------------------
# Stage 1 — Seed load (primary source of truth)
# ---------------------------------------------------------------------------

def load_seed(seed_path: Path) -> list[dict]:
    rows = _load_yaml(seed_path) or []
    out = []
    for r in rows:
        out.append({
            "entity": {
                "id": r["id"],
                "name": r["name"],
                "type": r.get("type", "sfo"),
                "country": r["country"],
                "region": region_for_country(r["country"]),
                "controlling_family": r.get("controlling_family"),
                "controllers": r.get("controllers"),
                "ticker": None,
                "exchange": None,
                "estimated_aum_usd": r.get("estimated_aum_usd"),
                "aum_basis": r.get("aum_basis", "estimate"),
                "ownership_pct": None,
                "sectors": r.get("sectors"),
                "deployment": r.get("deployment", "unknown"),
                "accessibility": r.get("accessibility", "unknown"),
                "thesis_blurb": None,
                "data_quality": 0,  # computed below
                "updated_at": NOW,
            },
            "sources": [
                {
                    "field": "estimated_aum_usd",
                    "source_type": "curated",
                    "url": r.get("source_url"),
                    "note": r.get("note"),
                    "retrieved_at": NOW,
                }
            ],
            # extra metadata used by enrichment passes
            "_source_url": r.get("source_url"),
            "_linkedin_url": r.get("linkedin_url"),
        })
    return out


# ---------------------------------------------------------------------------
# Stage 2 — Optional Exa discovery pass
# ---------------------------------------------------------------------------

TIER1 = ["HK", "JP", "SG", "IN", "KR", "AU", "CN"]
TIER2 = ["MY", "ID", "TH", "PH", "NZ", "VN"]

EXA_QUERIES = [
    "family office {country} 2025",
    "{country} family-controlled holding company investment",
    "{country} single family office investment vehicle",
]


def run_discovery(countries: list[str], out_dir: Path) -> None:
    """Run Exa searches for each country and log candidates (does not add entities)."""
    if not os.environ.get("EXA_API_KEY"):
        log.info("[discover] EXA_API_KEY not set — skipping discovery pass")
        return

    country_names = {
        "HK": "Hong Kong", "JP": "Japan", "SG": "Singapore",
        "IN": "India", "KR": "South Korea", "AU": "Australia", "CN": "China",
        "MY": "Malaysia", "ID": "Indonesia", "TH": "Thailand",
        "PH": "Philippines", "NZ": "New Zealand", "VN": "Vietnam",
    }

    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for country in countries:
        name = country_names.get(country, country)
        for tmpl in EXA_QUERIES:
            query = tmpl.format(country=name)
            log.info("[discover] exa: %s", query)
            results = exa.search(query, n=5)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    candidates.append({"country": country, "query": query, **r})

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "discovery_candidates.json"
    out_path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    log.info("[discover] %d candidates written to %s", len(candidates), out_path)


# ---------------------------------------------------------------------------
# Stage 3 — Optional per-source enrichment pass
# ---------------------------------------------------------------------------

def run_enrichment_sources(merged: list[dict]) -> list[write_db.Activity]:
    """Enrich entities via Crunchbase, Apollo, LinkedIn, Firecrawl. Returns new Activity rows."""
    activities: list[write_db.Activity] = []
    has_crunchbase = bool(os.environ.get("CRUNCHBASE_API_KEY"))
    has_apollo = bool(os.environ.get("APOLLO_API_KEY"))
    has_linkedin = bool(os.environ.get("LINKEDIN_API_KEY"))
    has_firecrawl = bool(os.environ.get("FIRECRAWL_API_KEY"))

    for row in merged:
        e = row["entity"]
        entity_id = e["id"]
        name = e["name"]

        # --- Crunchbase ---
        if has_crunchbase:
            org = crunchbase.find_org(name)
            if org:
                if not e.get("sectors") and org.get("short_description"):
                    pass  # description captured in source note only
                row["sources"].append({
                    "field": "name",
                    "source_type": "crunchbase",
                    "url": None,
                    "note": org.get("short_description") or f"Crunchbase match for {name}",
                    "retrieved_at": NOW,
                })
                if org.get("total_funding_usd") and not e.get("estimated_aum_usd"):
                    e["estimated_aum_usd"] = org["total_funding_usd"]
                    e["aum_basis"] = "disclosed"
                    row["sources"].append({
                        "field": "estimated_aum_usd",
                        "source_type": "crunchbase",
                        "url": None,
                        "note": f"total_funding_usd from Crunchbase",
                        "retrieved_at": NOW,
                    })
                deals = crunchbase.recent_deals(name, limit=5)
                for deal in deals:
                    activities.append(write_db.Activity(
                        entity_id=entity_id,
                        date=deal.get("date"),
                        kind="deal",
                        description=deal.get("description") or "Funding round",
                        source_url=deal.get("source_url"),
                    ))

        # --- Apollo ---
        if has_apollo:
            org_info = apollo.org_lookup(name)
            if org_info:
                if not e.get("sectors") and org_info.get("industry"):
                    e["sectors"] = [org_info["industry"]]
                row["sources"].append({
                    "field": "sectors",
                    "source_type": "apollo",
                    "url": org_info.get("website") or None,
                    "note": (
                        f"Apollo: industry={org_info.get('industry')}, "
                        f"employees={org_info.get('employees')}, "
                        f"founded={org_info.get('founded_year')}"
                    ),
                    "retrieved_at": NOW,
                })

        # --- LinkedIn ---
        if has_linkedin:
            li_url = row.get("_linkedin_url")
            if li_url:
                from ingest.sources import linkedin  # lazy import
                co = linkedin.company_profile(li_url)
                if co:
                    if not e.get("sectors") and co.get("industry"):
                        e["sectors"] = [co["industry"]]
                    row["sources"].append({
                        "field": "sectors",
                        "source_type": "linkedin",
                        "url": li_url,
                        "note": (
                            f"LinkedIn: employees={co.get('employee_count')}, "
                            f"country={co.get('headquarter_country')}"
                        ),
                        "retrieved_at": NOW,
                    })

        # --- Firecrawl ---
        if has_firecrawl:
            src_url = row.get("_source_url")
            if src_url:
                text = firecrawl.scrape(src_url)
                if text:
                    snippet = text[:500].replace("\n", " ")
                    row["sources"].append({
                        "field": "name",
                        "source_type": "firecrawl",
                        "url": src_url,
                        "note": snippet,
                        "retrieved_at": NOW,
                    })

    return activities


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=Path("ingest/config.yaml"))
    ap.add_argument("--enrich", action="store_true",
                    help="LLM enrichment via OpenRouter")
    ap.add_argument("--discover", action="store_true",
                    help="Exa discovery pass — writes data/discovery_candidates.json")
    ap.add_argument("--enrich-sources", action="store_true",
                    help="Per-source enrichment via Crunchbase, Apollo, LinkedIn, Firecrawl")
    args = ap.parse_args()

    cfg = _load_yaml(args.config)

    # Stage 1: Seed load
    seed = load_seed(Path("ingest/seeds/private_offices.yaml"))
    log.info("[seed] loaded %d entries", len(seed))

    # Dedupe seed on (country, controlling_family/name)
    seen_keys: set[tuple] = set()
    merged: list[dict] = []
    for row in seed:
        e = row["entity"]
        key = (e["country"], (e.get("controlling_family") or e["name"]).lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(row)

    # Stage 2: Optional Exa discovery (logs candidates, does NOT add entities)
    if args.discover:
        data_dir = args.out.parent
        run_discovery(TIER1 + TIER2, data_dir)

    # Stage 3: Optional per-source enrichment
    extra_activities: list[write_db.Activity] = []
    if args.enrich_sources:
        log.info("[enrich-sources] starting per-source enrichment pass")
        extra_activities = run_enrichment_sources(merged)
        log.info("[enrich-sources] produced %d activity rows", len(extra_activities))

    # Set data quality (post-enrichment so sources are counted)
    for row in merged:
        e = row["entity"]
        e["data_quality"] = infer_data_quality(
            aum_basis=e.get("aum_basis"),
            controllers=e.get("controllers"),
            recent_activity_count=0,
        )

    # Stage 4: LLM enrichment (gated on --enrich)
    if args.enrich and os.environ.get("OPENROUTER_API_KEY"):
        log.info("[enrich] running LLM enrichment pass")
        for row in merged:
            extra = enrich(row["entity"])
            if extra:
                row["entity"].setdefault("thesis_blurb", extra.get("thesis_blurb"))
                if row["entity"].get("deployment") == "unknown":
                    row["entity"]["deployment"] = extra.get("deployment", "unknown")
                if row["entity"].get("accessibility") == "unknown":
                    row["entity"]["accessibility"] = extra.get("accessibility", "unknown")
                row["sources"].append({
                    "field": "thesis_blurb",
                    "source_type": "llm:openrouter",
                    "url": None,
                    "note": "Generated by owl-alpha",
                    "retrieved_at": NOW,
                })

    # Stage 5: Sanity check
    if len(merged) < cfg["sanity"]["min_total_entities"]:
        raise SystemExit(
            f"Sanity check failed: only {len(merged)} entities "
            f"(min {cfg['sanity']['min_total_entities']}). Expand seed list."
        )

    # Stage 6: Write DB
    entities = [write_db.Entity(**row["entity"]) for row in merged]
    sources: list[write_db.Source] = []
    for row in merged:
        for s in row["sources"]:
            # Strip internal-only keys before constructing Source
            sources.append(write_db.Source(entity_id=row["entity"]["id"], **{
                k: v for k, v in s.items()
                if k in ("field", "source_type", "url", "note", "retrieved_at")
            }))

    write_db.build_db(args.out, entities, sources, extra_activities, [])
    log.info("[write] %d entities -> %s", len(entities), args.out)


if __name__ == "__main__":
    main()
