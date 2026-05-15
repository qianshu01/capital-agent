"""Build the capital.db SQLite file from in-memory dataclasses."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE entities (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  type            TEXT NOT NULL,
  country         TEXT NOT NULL,
  region          TEXT NOT NULL,
  controlling_family TEXT,
  controllers     TEXT,
  ticker          TEXT,
  exchange        TEXT,
  estimated_aum_usd REAL,
  aum_basis       TEXT,
  ownership_pct   REAL,
  sectors         TEXT,
  deployment      TEXT,
  accessibility   TEXT,
  thesis_blurb    TEXT,
  data_quality    INTEGER NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX idx_entities_country ON entities(country);
CREATE INDEX idx_entities_type    ON entities(type);
CREATE INDEX idx_entities_aum     ON entities(estimated_aum_usd);

CREATE TABLE sources (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  field       TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url         TEXT,
  note        TEXT,
  retrieved_at TEXT NOT NULL
);
CREATE INDEX idx_sources_entity ON sources(entity_id);

CREATE TABLE activities (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  date        TEXT,
  kind        TEXT NOT NULL,
  description TEXT NOT NULL,
  source_url  TEXT
);
CREATE INDEX idx_activities_entity ON activities(entity_id);

CREATE TABLE assumptions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  text        TEXT NOT NULL
);
"""

@dataclass
class Entity:
    id: str
    name: str
    type: str
    country: str
    region: str
    controlling_family: str | None
    controllers: list[str] | None
    ticker: str | None
    exchange: str | None
    estimated_aum_usd: float | None
    aum_basis: str | None
    ownership_pct: float | None
    sectors: list[str] | None
    deployment: str | None
    accessibility: str | None
    thesis_blurb: str | None
    data_quality: int
    updated_at: str

@dataclass
class Source:
    entity_id: str
    field: str
    source_type: str
    url: str | None
    note: str | None
    retrieved_at: str

@dataclass
class Activity:
    entity_id: str
    date: str | None
    kind: str
    description: str
    source_url: str | None

@dataclass
class Assumption:
    entity_id: str
    text: str

def _entity_row(e: Entity) -> tuple:
    return (
        e.id, e.name, e.type, e.country, e.region,
        e.controlling_family,
        json.dumps(e.controllers) if e.controllers is not None else None,
        e.ticker, e.exchange,
        e.estimated_aum_usd, e.aum_basis, e.ownership_pct,
        json.dumps(e.sectors) if e.sectors is not None else None,
        e.deployment, e.accessibility, e.thesis_blurb,
        e.data_quality, e.updated_at,
    )

def build_db(
    out: Path,
    entities: Iterable[Entity],
    sources: Iterable[Source],
    activities: Iterable[Activity],
    assumptions: Iterable[Assumption],
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(out)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [_entity_row(e) for e in entities],
        )
        conn.executemany(
            "INSERT INTO sources(entity_id,field,source_type,url,note,retrieved_at)"
            " VALUES (?,?,?,?,?,?)",
            [(s.entity_id, s.field, s.source_type, s.url, s.note, s.retrieved_at)
             for s in sources],
        )
        conn.executemany(
            "INSERT INTO activities(entity_id,date,kind,description,source_url)"
            " VALUES (?,?,?,?,?)",
            [(a.entity_id, a.date, a.kind, a.description, a.source_url)
             for a in activities],
        )
        conn.executemany(
            "INSERT INTO assumptions(entity_id,text) VALUES (?,?)",
            [(a.entity_id, a.text) for a in assumptions],
        )
        conn.commit()
    finally:
        conn.close()
