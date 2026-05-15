"""Ingestion orchestrator. Idempotent given fixed inputs.

Usage:
  python -m ingest.run --out data/capital.db [--enrich] [--config ingest/config.yaml]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

import yaml

from ingest import write_db
from ingest.classify import (
    is_family_holder, region_for_country, infer_data_quality,
)
from ingest.sources import mcp_finnhub, mcp_polygon
from ingest.enrich_llm import enrich

NOW = dt.datetime.utcnow().isoformat() + "Z"

def _slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")

def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text())

def discover_listed(country: str, cap: int, known_families: dict) -> list[dict]:
    """Return [{entity_dict, sources, holders}] for family-controlled listed cos."""
    raw = mcp_finnhub.list_companies(country, cap)
    if not raw:
        raw = mcp_polygon.list_companies(country, cap)
    out = []
    for co in raw:
        ticker = co.get("ticker")
        if not ticker or not co.get("name"):
            continue
        holders = mcp_finnhub.top_holders(ticker, limit=10)
        family_holder = next(
            (h for h in holders
             if is_family_holder(h.get("name") or "",
                                 country=country, known=known_families)),
            None,
        )
        if not family_holder:
            continue
        ownership_pct = family_holder.get("pct")
        if ownership_pct is None or ownership_pct < 0:
            continue
        family_name = (family_holder.get("name") or "").split()[0]
        out.append({
            "entity": {
                "id": _slug(f"{country}-{co['name']}"),
                "name": co["name"],
                "type": "listed_holding",
                "country": country,
                "region": region_for_country(country),
                "controlling_family": family_name,
                "controllers": [family_holder.get("name")],
                "ticker": ticker,
                "exchange": co.get("exchange"),
                "estimated_aum_usd": co.get("market_cap"),
                "aum_basis": "market_cap",
                "ownership_pct": ownership_pct,
                "sectors": [co.get("industry")] if co.get("industry") else None,
                "deployment": "direct",
                "accessibility": "restricted",
                "thesis_blurb": None,
                "data_quality": 4,
                "updated_at": NOW,
            },
            "sources": [
                {"field": "estimated_aum_usd", "source_type": "mcp:finnhub",
                 "url": None,
                 "note": f"Market cap from finnhub for {ticker}",
                 "retrieved_at": NOW},
                {"field": "ownership_pct", "source_type": "mcp:finnhub",
                 "url": None,
                 "note": f"Top holder {family_holder.get('name')} pct={ownership_pct}",
                 "retrieved_at": NOW},
            ],
        })
    return out

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
                "data_quality": 0,  # set below
                "updated_at": NOW,
            },
            "sources": [
                {"field": "estimated_aum_usd", "source_type": "curated",
                 "url": r.get("source_url"), "note": r.get("note"),
                 "retrieved_at": NOW}
            ],
        })
    return out

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=Path("ingest/config.yaml"))
    ap.add_argument("--enrich", action="store_true")
    args = ap.parse_args()

    cfg = _load_yaml(args.config)
    known = _load_yaml(Path("ingest/seeds/known_families.yaml"))
    seed = load_seed(Path("ingest/seeds/private_offices.yaml"))

    discovered: list[dict] = []
    for country in cfg["tiers"]["tier1"] + cfg["tiers"]["tier2"]:
        print(f"[discover] {country}")
        discovered.extend(
            discover_listed(country, cfg["listed"]["cap_per_country"], known)
        )

    # Dedupe: prefer seed over discovered when controlling_family matches in country
    seen_keys = set()
    merged: list[dict] = []
    for row in seed + discovered:
        e = row["entity"]
        key = (e["country"], (e.get("controlling_family") or e["name"]).lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(row)

    # Set data quality (post-merge so we know about activity later)
    for row in merged:
        e = row["entity"]
        e["data_quality"] = infer_data_quality(
            aum_basis=e.get("aum_basis"),
            controllers=e.get("controllers"),
            recent_activity_count=0,  # activities are seeded separately; refine later
        )

    # Enrichment
    if args.enrich and os.environ.get("OPENROUTER_API_KEY"):
        for row in merged:
            extra = enrich(row["entity"])
            if extra:
                row["entity"].setdefault("thesis_blurb", extra.get("thesis_blurb"))
                if row["entity"].get("deployment") == "unknown":
                    row["entity"]["deployment"] = extra.get("deployment", "unknown")
                if row["entity"].get("accessibility") == "unknown":
                    row["entity"]["accessibility"] = extra.get("accessibility", "unknown")
                row["sources"].append({
                    "field": "thesis_blurb", "source_type": "llm:openrouter",
                    "url": None, "note": "Generated by owl-alpha",
                    "retrieved_at": NOW,
                })

    if len(merged) < cfg["sanity"]["min_total_entities"]:
        raise SystemExit(
            f"Sanity check failed: only {len(merged)} entities (min "
            f"{cfg['sanity']['min_total_entities']}). Expand seed list."
        )

    entities = [write_db.Entity(**row["entity"]) for row in merged]
    sources: list[write_db.Source] = []
    for row in merged:
        for s in row["sources"]:
            sources.append(write_db.Source(entity_id=row["entity"]["id"], **s))

    write_db.build_db(args.out, entities, sources, [], [])
    print(f"[write] {len(entities)} entities -> {args.out}")

if __name__ == "__main__":
    main()
