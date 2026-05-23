# tests/ingest/test_migrate_evidence.py
import sqlite3
from pathlib import Path
from ingest.write_db import build_db, Entity
from ingest.migrate_evidence import migrate

def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "t.db"
    e = Entity(id="x", name="X", type="sfo", country="HK", region="East Asia",
               controlling_family=None, controllers=None, ticker=None,
               exchange=None, estimated_aum_usd=None, aum_basis="unknown",
               ownership_pct=None, sectors=None, deployment="unknown",
               accessibility="unknown", thesis_blurb=None,
               data_quality=1, updated_at="2026-05-23T00:00:00Z")
    build_db(db, [e], [], [], [])
    return db

def test_migration_adds_columns_and_table(tmp_path):
    db = _seed(tmp_path)
    migrate(db)
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)")}
    assert "provenance" in cols and "confidence_score" in cols
    src_cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)")}
    assert "evidence_id" in src_cols
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "evidence" in tables
    # default values
    row = conn.execute("SELECT provenance, confidence_score FROM entities").fetchone()
    assert row == ("curated", 3)

def test_migration_is_idempotent(tmp_path):
    db = _seed(tmp_path)
    migrate(db)
    migrate(db)  # second run must not raise
    conn = sqlite3.connect(db)
    # no duplicate evidence table, no doubled columns
    cols = [r[1] for r in conn.execute("PRAGMA table_info(entities)")]
    assert cols.count("provenance") == 1
