# tests/backend/test_entity_with_evidence.py
import importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ingest.write_db import build_db
from ingest.migrate_evidence import migrate
from backend.db import commit_evidence_bundle

@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    db = tmp_path / "t.db"
    build_db(db, [], [], [], [])
    migrate(db)
    monkeypatch.setenv("DB_PATH", str(db))
    import backend.db
    importlib.reload(backend.db)
    from backend.db import commit_evidence_bundle as _commit
    _commit({
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
            {"question_key": "where_capital_sits", "answer": "SFO Bangalore.",
             "confidence": 5, "source_urls": ["https://x.com"]},
            {"question_key": "how_much_capital", "answer": "$10B disclosed.",
             "confidence": 5, "source_urls": ["https://x.com"]},
            {"question_key": "who_controls", "answer": "Azim Premji, Atul Gupta (CIO).",
             "confidence": 5, "source_urls": ["https://x.com"]},
            {"question_key": "how_deployed", "answer": "Mixed.",
             "confidence": 4, "source_urls": ["https://x.com"]},
            {"question_key": "direct_or_external", "answer": "~60% direct.",
             "confidence": 3, "source_urls": ["https://x.com"]},
        ],
        "sources": [
            {"url": "https://x.com", "source_type": "firecrawl", "note": "n",
             "retrieved_at": "2026-05-23T00:00:00Z"},
        ],
    })
    from backend.main import app
    return TestClient(app)

def test_detail_includes_evidence(client):
    r = client.get("/api/entities/in-premji-invest")
    assert r.status_code == 200
    body = r.json()
    keys = {ev["question_key"] for ev in body["evidence"]}
    assert {"where_capital_sits", "how_much_capital", "who_controls",
            "how_deployed", "direct_or_external"} <= keys
    assert body["sources"][0]["url"] == "https://x.com"
