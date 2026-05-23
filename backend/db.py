"""Read-side SQLite session in WAL mode."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", "data/capital.db"))

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA query_only=ON;")
    return conn

@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


import datetime as _dt
import json as _json
import sqlite3 as _sqlite3
from backend.research.validator import validate_bundle as _validate

def _slug(s: str, country: str) -> str:
    base = "".join(c.lower() if c.isalnum() else "-" for c in f"{country}-{s}")
    return base.strip("-")

def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat() + "Z"

def commit_evidence_bundle(bundle: dict) -> dict:
    """Validate + upsert entity, evidence, sources. Returns
    {entity_id, status: 'ok'|'rejected', errors: [..]}."""
    errors = _validate(bundle)
    if errors:
        return {"entity_id": None, "status": "rejected", "errors": errors}

    e = bundle["entity"]
    eid = _slug(e["name"], e["country"])
    now = _now_iso()

    # Open writable connection (the read connection in get_conn() is query_only).
    conn = _sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        existing = conn.execute(
            "SELECT id FROM entities WHERE id=?", (eid,)
        ).fetchone()

        if existing is None:
            conn.execute(
                "INSERT INTO entities (id,name,type,country,region,"
                "controlling_family,controllers,ticker,exchange,"
                "estimated_aum_usd,aum_basis,ownership_pct,sectors,"
                "deployment,accessibility,thesis_blurb,data_quality,"
                "updated_at,provenance,confidence_score) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, e["name"], e["type"], e["country"], e["region"],
                 e.get("controlling_family"),
                 _json.dumps(e.get("controllers")) if e.get("controllers") else None,
                 e.get("ticker"), e.get("exchange"),
                 e.get("estimated_aum_usd"), e.get("aum_basis"),
                 e.get("ownership_pct"),
                 _json.dumps(e.get("sectors")) if e.get("sectors") else None,
                 e.get("deployment"), e.get("accessibility"),
                 e.get("thesis_blurb"), 3, now,
                 e["provenance"], e["confidence_score"]),
            )
        else:
            conn.execute(
                "UPDATE entities SET provenance=?, confidence_score=?, "
                "updated_at=? WHERE id=?",
                (e["provenance"], e["confidence_score"], now, eid),
            )

        # Build a lookup from url -> source metadata for later use
        url_to_src_meta: dict[str, dict] = {s["url"]: s for s in bundle["sources"]}

        # Evidence: upsert via UNIQUE(entity_id, question_key)
        for ev in bundle["evidence"]:
            existing_ev = conn.execute(
                "SELECT id FROM evidence WHERE entity_id=? AND question_key=?",
                (eid, ev["question_key"]),
            ).fetchone()
            if existing_ev:
                ev_id = existing_ev[0]
                conn.execute(
                    "UPDATE evidence SET answer=?, confidence=?, created_at=? "
                    "WHERE id=?",
                    (ev["answer"], ev["confidence"], now, ev_id),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO evidence (entity_id,question_key,answer,"
                    "confidence,created_at) VALUES (?,?,?,?,?)",
                    (eid, ev["question_key"], ev["answer"],
                     ev["confidence"], now),
                )
                ev_id = cur.lastrowid
            # Insert one source row per cited URL for this evidence item
            for u in ev.get("source_urls") or []:
                s_meta = url_to_src_meta.get(u, {})
                conn.execute(
                    "INSERT INTO sources (entity_id,field,source_type,url,note,"
                    "retrieved_at,evidence_id) VALUES (?,?,?,?,?,?,?)",
                    (eid, "evidence_citation",
                     s_meta.get("source_type", "exa"), u,
                     s_meta.get("note"), s_meta.get("retrieved_at") or now,
                     ev_id),
                )

        conn.commit()
    finally:
        conn.close()

    return {"entity_id": eid, "status": "ok", "errors": []}
