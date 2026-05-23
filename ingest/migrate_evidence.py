"""Idempotent schema migration to add evidence table + provenance columns."""
from __future__ import annotations
import sqlite3
from pathlib import Path

def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return col in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None

def migrate(db_path: Path | str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        if not _has_column(conn, "entities", "provenance"):
            conn.execute(
                "ALTER TABLE entities ADD COLUMN provenance TEXT "
                "NOT NULL DEFAULT 'curated'"
            )
        if not _has_column(conn, "entities", "confidence_score"):
            conn.execute(
                "ALTER TABLE entities ADD COLUMN confidence_score INTEGER "
                "NOT NULL DEFAULT 3"
            )
        if not _has_column(conn, "sources", "evidence_id"):
            conn.execute(
                "ALTER TABLE sources ADD COLUMN evidence_id INTEGER "
                "REFERENCES evidence(id)"
            )
        if not _has_table(conn, "evidence"):
            conn.executescript("""
                CREATE TABLE evidence (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entity_id TEXT NOT NULL REFERENCES entities(id),
                  question_key TEXT NOT NULL,
                  answer TEXT NOT NULL,
                  confidence INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  UNIQUE(entity_id, question_key)
                );
                CREATE INDEX idx_evidence_entity ON evidence(entity_id);
            """)
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    migrate(sys.argv[1] if len(sys.argv) > 1 else "data/capital.db")
    print("migration done")
