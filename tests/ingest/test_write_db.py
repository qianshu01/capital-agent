import sqlite3
from pathlib import Path
from ingest.write_db import build_db, Entity, Source, Activity, Assumption

def test_build_db_creates_schema_and_inserts_entity(tmp_path: Path):
    out = tmp_path / "test.db"
    entity = Entity(
        id="hk-test",
        name="Test Holdings",
        type="listed_holding",
        country="HK",
        region="East Asia",
        controlling_family="Test Family",
        controllers=["A. Test"],
        ticker="0001.HK",
        exchange="HKEX",
        estimated_aum_usd=1_000_000_000.0,
        aum_basis="market_cap",
        ownership_pct=42.0,
        sectors=["telecom"],
        deployment="direct",
        accessibility="restricted",
        thesis_blurb="Test blurb.",
        data_quality=4,
        updated_at="2026-05-15T00:00:00Z",
    )
    sources = [Source(entity_id="hk-test", field="estimated_aum_usd",
                      source_type="mcp:polygon", url="https://x", note=None,
                      retrieved_at="2026-05-15T00:00:00Z")]
    activities = [Activity(entity_id="hk-test", date="2026-04-01", kind="deal",
                           description="Sample deal", source_url="https://y")]
    assumptions = [Assumption(entity_id="hk-test", text="AUM = market cap")]

    build_db(out, [entity], sources, activities, assumptions)

    conn = sqlite3.connect(out)
    rows = conn.execute("SELECT name, country, data_quality FROM entities").fetchall()
    assert rows == [("Test Holdings", "HK", 4)]
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM assumptions").fetchone()[0] == 1
    # WAL is set per-connection at runtime, but indexes should exist
    idx = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    assert any("idx_entities_country" in r[0] for r in idx)
