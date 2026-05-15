import os
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from ingest.write_db import build_db, Entity

@pytest.fixture
def fixture_db(tmp_path: Path, monkeypatch) -> Path:
    db = tmp_path / "test.db"
    entities = [
        Entity(id="hk-a", name="Cheung Kong Holdings", type="listed_holding",
               country="HK", region="East Asia",
               controlling_family="Li", controllers=["Li Ka-shing"],
               ticker="0001.HK", exchange="HKEX",
               estimated_aum_usd=2.84e10, aum_basis="market_cap",
               ownership_pct=43.0, sectors=["telecom"],
               deployment="direct", accessibility="restricted",
               thesis_blurb=None, data_quality=4,
               updated_at="2026-05-15T00:00:00Z"),
        Entity(id="in-premji", name="Premji Invest", type="sfo",
               country="IN", region="South Asia",
               controlling_family="Premji", controllers=["Azim Premji"],
               ticker=None, exchange=None,
               estimated_aum_usd=1.0e10, aum_basis="disclosed",
               ownership_pct=None, sectors=["tech"],
               deployment="mixed", accessibility="restricted",
               thesis_blurb=None, data_quality=5,
               updated_at="2026-05-15T00:00:00Z"),
        Entity(id="sg-tsao", name="Tsao Family Office", type="sfo",
               country="SG", region="SEA",
               controlling_family="Tsao", controllers=["Frederick Tsao"],
               ticker=None, exchange=None,
               estimated_aum_usd=2.5e9, aum_basis="estimate",
               ownership_pct=None, sectors=["shipping"],
               deployment="mixed", accessibility="closed",
               thesis_blurb=None, data_quality=3,
               updated_at="2026-05-15T00:00:00Z"),
    ]
    build_db(db, entities, [], [], [])
    monkeypatch.setenv("DB_PATH", str(db))
    return db

@pytest.fixture
def client(fixture_db) -> TestClient:
    # Reload backend.db to pick up the env var
    import importlib, backend.db
    importlib.reload(backend.db)
    from backend.main import app
    return TestClient(app)
