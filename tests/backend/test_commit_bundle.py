# tests/backend/test_commit_bundle.py
import importlib
from pathlib import Path
import pytest
from ingest.write_db import build_db, Entity
from ingest.migrate_evidence import migrate

@pytest.fixture
def db(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "t.db"
    build_db(p, [], [], [], [])
    migrate(p)
    monkeypatch.setenv("DB_PATH", str(p))
    import backend.db
    importlib.reload(backend.db)
    return p

def _bundle():
    return {
        "entity": {
            "name": "Premji Invest", "type": "sfo", "country": "IN",
            "region": "South Asia", "controlling_family": "Premji",
            "ticker": None, "exchange": None,
            "estimated_aum_usd": 1e10, "aum_basis": "disclosed",
            "sectors": ["tech"], "deployment": "mixed",
            "accessibility": "restricted",
            "provenance": "chat_discovered", "confidence_score": 4,
        },
        "evidence": [
            {"question_key": "where_capital_sits", "answer": "SFO in Bangalore.",
             "confidence": 5, "source_urls": ["https://x.com"]},
            {"question_key": "how_much_capital", "answer": "$10B disclosed.",
             "confidence": 5, "source_urls": ["https://x.com"]},
            {"question_key": "who_controls", "answer": "Azim Premji, Atul Gupta (CIO).",
             "confidence": 5, "source_urls": ["https://x.com"]},
            {"question_key": "how_deployed", "answer": "Mixed direct/external.",
             "confidence": 4, "source_urls": ["https://x.com"]},
            {"question_key": "direct_or_external", "answer": "~60% direct.",
             "confidence": 3, "source_urls": ["https://x.com"]},
        ],
        "sources": [
            {"url": "https://x.com", "source_type": "firecrawl",
             "note": "n", "retrieved_at": "2026-05-23T00:00:00Z"},
        ],
    }

def test_commit_writes_entity_evidence_sources(db):
    from backend.db import commit_evidence_bundle
    res = commit_evidence_bundle(_bundle())
    assert res["status"] == "ok"
    assert res["errors"] == []
    eid = res["entity_id"]
    import sqlite3
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE id=?",
                        (eid,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM evidence WHERE entity_id=?",
                        (eid,)).fetchone()[0] == 5
    # every evidence row should have at least one matching source row with FK
    assert conn.execute(
        "SELECT COUNT(*) FROM sources WHERE entity_id=? AND evidence_id IS NOT NULL",
        (eid,)
    ).fetchone()[0] >= 5

def test_commit_rejects_invalid(db):
    from backend.db import commit_evidence_bundle
    bad = _bundle()
    bad["entity"]["provenance"] = "wrong"
    res = commit_evidence_bundle(bad)
    assert res["status"] == "rejected"
    assert any("provenance" in e for e in res["errors"])

def test_commit_enriched_reuses_entity(db):
    from backend.db import commit_evidence_bundle
    first = commit_evidence_bundle(_bundle())
    second_bundle = _bundle()
    second_bundle["entity"]["provenance"] = "chat_enriched"
    second_bundle["evidence"][0]["answer"] = "Updated narrative."
    second = commit_evidence_bundle(second_bundle)
    assert second["entity_id"] == first["entity_id"]
    import sqlite3
    conn = sqlite3.connect(db)
    # unique(entity_id, question_key) — should still be 5 rows, not 10
    n = conn.execute("SELECT COUNT(*) FROM evidence WHERE entity_id=?",
                     (first["entity_id"],)).fetchone()[0]
    assert n == 5
