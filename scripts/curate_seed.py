"""Non-interactive seed curation. Runs the chat loop per vehicle and commits."""
from __future__ import annotations
import argparse
import asyncio
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SEED = [
    # (name, country, type)
    ("Premji Invest", "IN", "sfo"),
    ("Tata Sons", "IN", "listed_holding"),
    ("Catamaran Ventures", "IN", "sfo"),
    ("RNT Associates", "IN", "sfo"),
    ("Bajaj Holdings & Investment", "IN", "listed_holding"),
    ("Horizons Ventures", "HK", "sfo"),
    ("CK Hutchison Holdings", "HK", "listed_holding"),
    ("Henderson Land Development", "HK", "listed_holding"),
    ("Tsao Family Office", "SG", "sfo"),
    ("Heliconia Capital", "SG", "sfo"),
    ("Sinar Mas Group", "ID", "listed_holding"),
    ("Djarum", "ID", "listed_holding"),
    ("Geely Holding Group", "CN", "listed_holding"),
    ("Wanda Group", "CN", "listed_holding"),
    ("Samsung C&T", "KR", "listed_holding"),
    ("Suntory Holdings", "JP", "listed_holding"),
    ("Tattarang", "AU", "sfo"),
    ("Hancock Prospecting", "AU", "sfo"),
    ("Central Group", "TH", "listed_holding"),
    ("Ayala Corporation", "PH", "listed_holding"),
    # +10 expansion (2026-05-25): high-AUM, family-controlled vehicles
    ("Genting Berhad", "MY", "listed_holding"),
    ("Mahindra & Mahindra", "IN", "listed_holding"),
    ("Sun Hung Kai Properties", "HK", "listed_holding"),
    ("New World Development", "HK", "listed_holding"),
    ("Salim Group", "ID", "listed_holding"),
    ("SK Holdings", "KR", "listed_holding"),
    ("LG Corp", "KR", "listed_holding"),
    ("JG Summit Holdings", "PH", "listed_holding"),
    ("Vingroup", "VN", "listed_holding"),
    ("SM Investments", "PH", "listed_holding"),
]

CURATE_PROMPT_TEMPLATE = """Research the investment vehicle "{name}" \
(country: {country}, type hint: {type_hint}).

Your goal: produce a complete evidence bundle and call `commit_entity` with \
provenance="curated" and confidence_score=4 (or 5 if disclosed by the entity itself).

Required workflow:
1. `query_db` filter by name to check duplicates.
2. `search_web` for the vehicle name + "AUM" / "CIO" / "investment strategy".
3. `scrape_url` the official site and at least one news/filing page.
4. For listed vehicles, call `finnhub_company` or `polygon_ticker_lookup`.
5. For private orgs, call `apollo_org_lookup`.
6. Compose a bundle answering all 7 questions (minimum 5) with citation URLs.
7. Call `commit_entity`. If rejected, fix the errors and retry.

Be brief in your final summary."""

async def curate_one(name: str, country: str, type_hint: str) -> None:
    from backend.research import loop, session
    sid = f"curator-{uuid.uuid4().hex[:8]}"
    prompt = CURATE_PROMPT_TEMPLATE.format(
        name=name, country=country, type_hint=type_hint
    )
    written = False
    error_msg = None
    async for ev in loop.run_turn(sid, prompt):
        e = ev["event"]
        d = ev.get("data") or {}
        if e == "tool_call":
            print(f"  [{name}] tool: {d.get('tool')} {str(d.get('args'))[:80]}")
        elif e == "db_write":
            print(f"  [{name}] WROTE {d.get('entity_id')}")
            written = True
        elif e == "error":
            error_msg = d.get("message")
            print(f"  [{name}] ERROR {error_msg}")
        elif e == "message":
            print(f"  [{name}] LLM: {(d.get('text') or '')[:120]}")
    if not written:
        print(f"  [{name}] !!! agent did not commit. Last error: {error_msg}")

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/capital.db")
    ap.add_argument("--only", help="Only curate names matching this substring.")
    args = ap.parse_args()

    import os
    os.environ["DB_PATH"] = str(Path(args.db).resolve())
    from ingest.migrate_evidence import migrate
    migrate(args.db)  # ensure schema is current
    import importlib, backend.db
    importlib.reload(backend.db)

    rows = SEED
    if args.only:
        rows = [r for r in rows if args.only.lower() in r[0].lower()]
    print(f"Curating {len(rows)} vehicles -> {args.db}")
    for name, country, type_hint in rows:
        print(f"\n=== {name} ({country}) ===")
        await curate_one(name, country, type_hint)

if __name__ == "__main__":
    asyncio.run(main())
