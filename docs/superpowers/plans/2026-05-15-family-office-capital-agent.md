# Family Office Capital Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-container web app that surfaces family-office and family-controlled capital pools across Asia, with structured filtering, a natural-language ask endpoint, and a Bloomberg-style dense data table UI.

**Architecture:** Build-time ingestion pipeline produces a seed SQLite DB shipped inside the image. Runtime is a FastAPI process serving three JSON endpoints plus the static React build, over HTTPS on :8443. SQLite lives on a writable Docker volume in WAL mode so `docker exec … ingest.run` can refresh it without restarting the backend.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, SQLite (stdlib `sqlite3`), pydantic v2, httpx, pyyaml, pytest. React 18 + Vite 5 + TypeScript, Tailwind CSS v3, TanStack Query v5, lucide-react. OpenRouter (`owl-alpha`) for LLM. MCP servers (Polygon, Finnhub, Alpha Vantage) at ingestion time only.

**Spec:** `docs/superpowers/specs/2026-05-15-family-office-capital-agent-design.md`

---

## File Structure

```
.
├── Dockerfile
├── Makefile
├── README.md
├── .gitignore
├── requirements.txt              # backend runtime deps
├── requirements-ingest.txt       # ingestion deps
├── docs/
│   ├── DATA.md
│   └── METHODOLOGY.md
├── scripts/
│   ├── gen-cert.sh
│   └── entrypoint.sh
├── ingest/
│   ├── __init__.py
│   ├── run.py                    # orchestrator + CLI
│   ├── config.yaml               # tier lists, thresholds, family dictionaries
│   ├── seeds/
│   │   ├── private_offices.yaml
│   │   └── known_families.yaml
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── mcp_polygon.py
│   │   ├── mcp_finnhub.py
│   │   └── mcp_alphavantage.py
│   ├── classify.py
│   ├── enrich_llm.py
│   └── write_db.py
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── db.py
│   ├── schemas.py
│   ├── llm.py
│   └── routers/
│       ├── __init__.py
│       ├── entities.py
│       ├── entity.py
│       └── ask.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts
│       ├── types.ts
│       ├── theme.css
│       └── components/
│           ├── TopBar.tsx
│           ├── FilterPanel.tsx
│           ├── EntityTable.tsx
│           ├── AskPanel.tsx
│           └── DetailView.tsx
└── tests/
    ├── ingest/
    │   ├── test_classify.py
    │   └── test_write_db.py
    └── backend/
        ├── conftest.py
        ├── test_entities.py
        ├── test_entity.py
        └── test_ask.py
```

Each unit has a single responsibility: ingestion modules never import backend code, backend never imports ingestion code, frontend talks to backend only via JSON.

---

## Phase 0 — Project skeleton

### Task 0.1: Scaffold repo

**Files:**
- Create: `.gitignore`
- Create: `Makefile`
- Create: `README.md`
- Create: `requirements.txt`
- Create: `requirements-ingest.txt`

- [ ] **Step 1: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.env
data/
node_modules/
frontend/dist/
backend/static/
*.db
*.db-journal
*.db-wal
*.db-shm
.pytest_cache/
.DS_Store
certs/
ingest/snapshot.json
```

- [ ] **Step 2: Write `requirements.txt`** (backend runtime)

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.2
httpx==0.27.2
```

- [ ] **Step 3: Write `requirements-ingest.txt`**

```
httpx==0.27.2
pyyaml==6.0.2
pydantic==2.9.2
```

- [ ] **Step 4: Write `Makefile`**

```makefile
.PHONY: ingest backend frontend test fmt clean

ingest:
	python -m ingest.run --out data/capital.db

backend:
	DB_PATH=data/capital.db uvicorn backend.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	pytest -q

clean:
	rm -rf data/*.db data/*.db-* frontend/dist backend/static
```

- [ ] **Step 5: Write `README.md`** (skeleton — fleshed out in Task 6.3)

```markdown
# Family Office Capital Agent

See `docs/superpowers/specs/2026-05-15-family-office-capital-agent-design.md` for design.
Run `make ingest && make backend` for local dev, or `docker build && docker run` (see `Dockerfile`) for the demo.
```

- [ ] **Step 6: Initialize git and commit**

```bash
git init
git add .gitignore Makefile README.md requirements.txt requirements-ingest.txt
git commit -m "chore: project skeleton"
```

Expected: `1 commit on main, 5 files`.

---

## Phase 1 — Data layer (TDD)

### Task 1.1: Schema + `write_db.py`

**Files:**
- Create: `ingest/__init__.py` (empty)
- Create: `ingest/write_db.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/ingest/__init__.py` (empty)
- Create: `tests/ingest/test_write_db.py`

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_write_db.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/ingest/test_write_db.py -v
```

Expected: `ImportError: No module named 'ingest.write_db'`.

- [ ] **Step 3: Implement `ingest/write_db.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

```bash
pytest tests/ingest/test_write_db.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/__init__.py ingest/write_db.py tests/__init__.py tests/ingest/
git commit -m "feat(ingest): write_db schema + dataclasses"
```

### Task 1.2: `classify.py` rules

**Files:**
- Create: `ingest/classify.py`
- Create: `tests/ingest/test_classify.py`

- [ ] **Step 1: Write the failing test**

```python
from ingest.classify import is_family_holder, region_for_country, infer_data_quality

def test_is_family_holder_rejects_corporate_suffixes():
    assert is_family_holder("BlackRock Inc") is False
    assert is_family_holder("Vanguard ETF Trust") is False
    assert is_family_holder("Temasek Holdings Pte Ltd") is False

def test_is_family_holder_accepts_individual_names():
    assert is_family_holder("Li Ka-shing") is True
    assert is_family_holder("Mukesh D. Ambani") is True

def test_is_family_holder_accepts_known_family_dict():
    families = {"HK": ["Li", "Kwok"]}
    assert is_family_holder("Li Family Trust", country="HK", known=families) is True
    assert is_family_holder("Acme Holdings", country="HK", known=families) is False

def test_region_for_country():
    assert region_for_country("HK") == "East Asia"
    assert region_for_country("ID") == "SEA"
    assert region_for_country("IN") == "South Asia"
    assert region_for_country("AU") == "Oceania"
    assert region_for_country("KZ") == "Central Asia"

def test_infer_data_quality():
    # disclosed AUM + controllers + recent activity -> 5
    assert infer_data_quality(aum_basis="disclosed", controllers=["A"], recent_activity_count=1) == 5
    # market cap + controllers + activity -> 4
    assert infer_data_quality(aum_basis="market_cap", controllers=["A"], recent_activity_count=1) == 4
    # estimated, family only -> 2
    assert infer_data_quality(aum_basis="estimate", controllers=None, recent_activity_count=0) == 2
    # nothing -> 1
    assert infer_data_quality(aum_basis=None, controllers=None, recent_activity_count=0) == 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/ingest/test_classify.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `ingest/classify.py`**

```python
"""Pure rule-based classification helpers. No I/O."""
from __future__ import annotations

import re

CORPORATE_PATTERN = re.compile(
    r"\b(Inc|Corp|Corporation|Ltd|Limited|Pte|Plc|GmbH|Trust\s+Co|Bank|Fund|"
    r"ETF|Pension|Sovereign|Capital|Asset\s+Mgmt|Asset\s+Management|"
    r"Securities|Holdings\s+Pte|Holdings\s+Inc|Investments\s+Inc)\b",
    re.IGNORECASE,
)

REGION_BY_COUNTRY = {
    # East Asia
    "CN": "East Asia", "HK": "East Asia", "JP": "East Asia",
    "KR": "East Asia", "MN": "East Asia",
    # SEA
    "SG": "SEA", "MY": "SEA", "ID": "SEA", "TH": "SEA", "PH": "SEA",
    "VN": "SEA", "KH": "SEA", "LA": "SEA", "MM": "SEA", "BN": "SEA",
    # South Asia
    "IN": "South Asia", "PK": "South Asia", "LK": "South Asia",
    "BD": "South Asia", "NP": "South Asia", "BT": "South Asia",
    # Oceania
    "AU": "Oceania", "NZ": "Oceania",
    # Central Asia
    "KZ": "Central Asia",
}

def region_for_country(code: str) -> str:
    return REGION_BY_COUNTRY.get(code.upper(), "Unknown")

def is_family_holder(
    name: str,
    *,
    country: str | None = None,
    known: dict[str, list[str]] | None = None,
) -> bool:
    """Return True if the holder name looks like an individual or known family."""
    if not name:
        return False
    if known and country and country.upper() in known:
        for fam in known[country.upper()]:
            if fam.lower() in name.lower():
                return True
    if CORPORATE_PATTERN.search(name):
        return False
    # Heuristic: 2+ alphabetic tokens, no digits → likely a personal name
    tokens = [t for t in re.split(r"[\s.\-]+", name) if t]
    if len(tokens) >= 2 and all(re.match(r"^[A-Za-z'\-]+$", t) for t in tokens):
        return True
    return False

def infer_data_quality(
    *,
    aum_basis: str | None,
    controllers: list[str] | None,
    recent_activity_count: int,
) -> int:
    has_controllers = bool(controllers)
    has_activity = recent_activity_count > 0
    if aum_basis == "disclosed" and has_controllers and has_activity:
        return 5
    if aum_basis == "market_cap" and has_controllers and has_activity:
        return 4
    if aum_basis in ("market_cap", "estimate") and (has_controllers or has_activity):
        return 3
    if aum_basis == "estimate":
        return 2
    return 1
```

- [ ] **Step 4: Run to verify it passes**

```bash
pytest tests/ingest/test_classify.py -v
```

Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add ingest/classify.py tests/ingest/test_classify.py
git commit -m "feat(ingest): classification rules"
```

### Task 1.3: Seed loader and config

**Files:**
- Create: `ingest/config.yaml`
- Create: `ingest/seeds/private_offices.yaml`
- Create: `ingest/seeds/known_families.yaml`

- [ ] **Step 1: Write `ingest/config.yaml`**

```yaml
tiers:
  tier1: [HK, JP, SG, IN, KR, AU, CN]
  tier2: [MY, ID, TH, PH, NZ, VN]
  tier3: [MM, LA, BT, BN, MN, PK, LK, BD, NP, KH, KZ]

ownership:
  family_min_pct: 25.0
  top_n_holders: 10

listed:
  cap_per_country: 100         # max companies fetched per country

sanity:
  min_total_entities: 50       # build fails below this
```

- [ ] **Step 2: Write `ingest/seeds/known_families.yaml`** (illustrative; expand during execution)

```yaml
HK:  [Li, Kwok, Lee, Cheng, Pao, Woo, Ng]
SG:  [Kwek, Khoo, Ng, Wee]
IN:  [Ambani, Adani, Tata, Birla, Mahindra, Premji, Murthy, Bajaj, Godrej, Hinduja]
ID:  [Hartono, Widjaja, Salim, Riady, Sampoerna]
TH:  [Chearavanont, Chirathivat, Sirivadhanabhakdi]
MY:  [Kuok, Lim, Ananda, Quek]
PH:  [Sy, Ayala, Aboitiz, Gokongwei, Tan]
KR:  [Lee, Chung, Koo, Shin, Cho]
JP:  [Toyoda, Suzuki, Mori]
AU:  [Rinehart, Forrest, Stokes, Lowy]
NZ:  [Hart, Mowbray]
CN:  [Wang, Liu, Ma, Zhang]
PK:  [Mansha, Dewan, Saigol]
BD:  [Rahimafrooz, Beximco]
LK:  [Hayleys, John Keells]
```

- [ ] **Step 3: Write `ingest/seeds/private_offices.yaml`** (≥30 entries; expand during execution. Schema must match `Entity` dataclass.)

```yaml
- id: in-premji-invest
  name: Premji Invest
  type: sfo
  country: IN
  controlling_family: Premji
  controllers: [Azim Premji, Rishad Premji]
  estimated_aum_usd: 10000000000
  aum_basis: disclosed
  sectors: [tech, consumer, financials]
  deployment: mixed
  accessibility: restricted
  source_url: https://premjiinvest.com/about
  note: Disclosed AUM per multiple press references.

- id: in-catamaran
  name: Catamaran Ventures
  type: sfo
  country: IN
  controlling_family: Murthy
  controllers: [N. R. Narayana Murthy]
  estimated_aum_usd: 1000000000
  aum_basis: estimate
  sectors: [tech, consumer]
  deployment: direct
  accessibility: restricted
  source_url: https://catamaranventures.in/
  note: AUM estimated from public deal history.

- id: sg-tsao-family-office
  name: Tsao Family Office
  type: sfo
  country: SG
  controlling_family: Tsao
  controllers: [Frederick Tsao]
  estimated_aum_usd: 2500000000
  aum_basis: estimate
  sectors: [shipping, real_estate, sustainability]
  deployment: mixed
  accessibility: closed
  source_url: https://www.tsaofamilyoffice.com/
  note: AUM range cited in industry press.

# ... continue with at least 30 entries spanning HK, JP, KR, AU, MY, ID, TH, PH,
# CN, NZ, VN, plus a handful of tier-3 placeholders. Each entry MUST include a
# source_url and a note explaining the AUM basis.
```

- [ ] **Step 4: Commit**

```bash
git add ingest/config.yaml ingest/seeds/
git commit -m "feat(ingest): config and curated seed lists"
```

---

## Phase 2 — Ingestion orchestration

### Task 2.1: MCP source clients (thin wrappers)

**Files:**
- Create: `ingest/sources/__init__.py` (empty)
- Create: `ingest/sources/mcp_polygon.py`
- Create: `ingest/sources/mcp_finnhub.py`
- Create: `ingest/sources/mcp_alphavantage.py`

Each module exposes the same surface so `run.py` can call any of them uniformly:

```python
def list_companies(country: str, limit: int) -> list[dict]: ...
def top_holders(ticker: str, limit: int = 10) -> list[dict]: ...
```

- [ ] **Step 1: Implement `ingest/sources/mcp_polygon.py`**

```python
"""Polygon.io MCP wrapper. Reads POLYGON_API_KEY from env."""
from __future__ import annotations

import os
import httpx

BASE = "https://api.polygon.io"

def _key() -> str:
    k = os.environ.get("POLYGON_API_KEY")
    if not k:
        raise RuntimeError("POLYGON_API_KEY not set")
    return k

def list_companies(country: str, limit: int) -> list[dict]:
    """Return [{ticker, name, exchange, market_cap, industry}, ...] for `country`.
    Polygon's reference endpoint covers US-listed primarily; for HK/SG/JP/etc.
    fall back to empty list and let other MCP sources cover the gap.
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{BASE}/v3/reference/tickers",
                params={"market": "stocks", "active": "true",
                        "limit": min(limit, 1000), "apiKey": _key()},
            )
            r.raise_for_status()
            data = r.json().get("results", [])
        return [
            {"ticker": t["ticker"], "name": t.get("name"),
             "exchange": t.get("primary_exchange"),
             "market_cap": t.get("market_cap"),
             "industry": t.get("sic_description")}
            for t in data
            if (t.get("locale") or "").upper() == country.upper()
        ][:limit]
    except Exception as e:
        print(f"[polygon] list_companies({country}) failed: {e}")
        return []

def top_holders(ticker: str, limit: int = 10) -> list[dict]:
    # Polygon does not expose holder lists in the free tier; return empty.
    return []
```

- [ ] **Step 2: Implement `ingest/sources/mcp_finnhub.py`**

```python
"""Finnhub MCP wrapper."""
from __future__ import annotations

import os
import httpx

BASE = "https://finnhub.io/api/v1"

def _key() -> str:
    k = os.environ.get("FINNHUB_API_KEY")
    if not k:
        raise RuntimeError("FINNHUB_API_KEY not set")
    return k

# Finnhub uses exchange codes (e.g. HK, T, KS, SI) rather than country codes.
EXCHANGE_BY_COUNTRY = {
    "HK": "HK", "JP": "T", "KR": "KS", "SG": "SI",
    "IN": "BO", "AU": "AX", "CN": "SS",
    "MY": "KL", "ID": "JK", "TH": "BK", "PH": "PS", "NZ": "NZ", "VN": "HM",
}

def list_companies(country: str, limit: int) -> list[dict]:
    code = EXCHANGE_BY_COUNTRY.get(country.upper())
    if not code:
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                f"{BASE}/stock/symbol",
                params={"exchange": code, "token": _key()},
            )
            r.raise_for_status()
            symbols = r.json()
        out: list[dict] = []
        for s in symbols[:limit]:
            tkr = s.get("symbol")
            try:
                p = client.get(
                    f"{BASE}/stock/profile2",
                    params={"symbol": tkr, "token": _key()},
                    timeout=10.0,
                )
                prof = p.json() if p.status_code == 200 else {}
            except Exception:
                prof = {}
            out.append({
                "ticker": tkr,
                "name": prof.get("name") or s.get("description"),
                "exchange": code,
                "market_cap": (prof.get("marketCapitalization") or 0) * 1_000_000,
                "industry": prof.get("finnhubIndustry"),
            })
        return out
    except Exception as e:
        print(f"[finnhub] list_companies({country}) failed: {e}")
        return []

def top_holders(ticker: str, limit: int = 10) -> list[dict]:
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{BASE}/stock/ownership",
                params={"symbol": ticker, "limit": limit, "token": _key()},
            )
            if r.status_code != 200:
                return []
            data = r.json().get("ownership", [])
        return [{"name": h.get("name"), "share": h.get("share"),
                 "pct": h.get("percent")} for h in data][:limit]
    except Exception as e:
        print(f"[finnhub] top_holders({ticker}) failed: {e}")
        return []
```

- [ ] **Step 3: Implement `ingest/sources/mcp_alphavantage.py`**

```python
"""Alpha Vantage wrapper used as a fallback for fundamentals."""
from __future__ import annotations

import os
import httpx

BASE = "https://www.alphavantage.co/query"

def _key() -> str:
    k = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not k:
        raise RuntimeError("ALPHAVANTAGE_API_KEY not set")
    return k

def list_companies(country: str, limit: int) -> list[dict]:
    # Alpha Vantage has no per-country listing endpoint in the free tier.
    return []

def top_holders(ticker: str, limit: int = 10) -> list[dict]:
    return []  # not in free tier
```

- [ ] **Step 4: Commit**

```bash
git add ingest/sources/
git commit -m "feat(ingest): MCP source wrappers (polygon/finnhub/alpha-vantage)"
```

### Task 2.2: LLM enrichment (gated)

**Files:**
- Create: `ingest/enrich_llm.py`

- [ ] **Step 1: Implement**

```python
"""Optional LLM enrichment via OpenRouter. Skipped when OPENROUTER_API_KEY is unset
or the run was invoked without --enrich."""
from __future__ import annotations

import json
import os
import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "owl-alpha")

PROMPT = (
    "Given this entity JSON, return a strict JSON object with keys "
    "thesis_blurb (1–2 sentences, factual, no marketing language), "
    "deployment (one of: direct, external_managers, mixed, unknown), "
    "accessibility (one of: open, restricted, closed, unknown). "
    "If you do not have evidence, set deployment/accessibility to 'unknown'. "
    "Return ONLY the JSON object."
)

def enrich(entity: dict) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": json.dumps(entity)},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            if r.status_code != 200:
                print(f"[enrich] {r.status_code}: {r.text[:200]}")
                return {}
            content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"[enrich] failed for {entity.get('id')}: {e}")
        return {}
```

- [ ] **Step 2: Commit**

```bash
git add ingest/enrich_llm.py
git commit -m "feat(ingest): optional LLM enrichment via OpenRouter"
```

### Task 2.3: Orchestrator `run.py`

**Files:**
- Create: `ingest/run.py`

- [ ] **Step 1: Implement**

```python
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
```

- [ ] **Step 2: Smoke run (without API keys, expect graceful fallback to seed-only)**

```bash
python -m ingest.run --out data/capital.db
```

Expected: prints `[discover] HK ...` lines (each may log MCP failures), then `[write] N entities -> data/capital.db` where N == size of seed list. Build will fail unless seed has ≥50 entries — expand `private_offices.yaml` until it does.

- [ ] **Step 3: Commit**

```bash
git add ingest/run.py
git commit -m "feat(ingest): orchestrator with seed + listed merge"
```

---

## Phase 3 — Backend (TDD)

### Task 3.1: DB layer + schemas

**Files:**
- Create: `backend/__init__.py` (empty)
- Create: `backend/db.py`
- Create: `backend/schemas.py`

- [ ] **Step 1: Implement `backend/db.py`**

```python
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
```

- [ ] **Step 2: Implement `backend/schemas.py`**

```python
"""Pydantic response models."""
from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, field_validator

class Entity(BaseModel):
    id: str
    name: str
    type: str
    country: str
    region: str
    controlling_family: str | None = None
    controllers: list[str] | None = None
    ticker: str | None = None
    exchange: str | None = None
    estimated_aum_usd: float | None = None
    aum_basis: str | None = None
    ownership_pct: float | None = None
    sectors: list[str] | None = None
    deployment: str | None = None
    accessibility: str | None = None
    thesis_blurb: str | None = None
    data_quality: int
    updated_at: str

    @field_validator("controllers", "sectors", mode="before")
    @classmethod
    def _parse_json(cls, v: Any):
        if isinstance(v, str):
            return json.loads(v)
        return v

class EntitiesPage(BaseModel):
    total: int
    results: list[Entity]

class Source(BaseModel):
    field: str
    source_type: str
    url: str | None = None
    note: str | None = None
    retrieved_at: str

class Activity(BaseModel):
    date: str | None = None
    kind: str
    description: str
    source_url: str | None = None

class EntityDetail(BaseModel):
    entity: Entity
    sources: list[Source]
    activities: list[Activity]
    assumptions: list[str]

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    entities: list[Entity]
    filters_used: dict
```

- [ ] **Step 3: Commit**

```bash
git add backend/__init__.py backend/db.py backend/schemas.py
git commit -m "feat(backend): db connection + pydantic schemas"
```

### Task 3.2: `GET /api/entities`

**Files:**
- Create: `backend/routers/__init__.py` (empty)
- Create: `backend/routers/entities.py`
- Create: `backend/main.py`
- Create: `tests/backend/__init__.py` (empty)
- Create: `tests/backend/conftest.py`
- Create: `tests/backend/test_entities.py`

- [ ] **Step 1: Write the failing test**

`tests/backend/conftest.py`:

```python
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
```

`tests/backend/test_entities.py`:

```python
def test_list_all(client):
    r = client.get("/api/entities")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["results"]) == 3

def test_filter_country(client):
    r = client.get("/api/entities?country=HK")
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == "hk-a"

def test_filter_min_aum(client):
    r = client.get("/api/entities?min_aum_usd=5000000000")
    ids = {e["id"] for e in r.json()["results"]}
    assert ids == {"hk-a", "in-premji"}

def test_sort_aum_desc(client):
    r = client.get("/api/entities?sort=aum_desc")
    results = r.json()["results"]
    assert [e["id"] for e in results] == ["hk-a", "in-premji", "sg-tsao"]

def test_q_substring(client):
    r = client.get("/api/entities?q=premji")
    assert r.json()["total"] == 1

def test_pagination(client):
    r = client.get("/api/entities?limit=1&offset=1&sort=aum_desc")
    body = r.json()
    assert body["total"] == 3
    assert len(body["results"]) == 1
    assert body["results"][0]["id"] == "in-premji"
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/backend/test_entities.py -v
```

Expected: ImportError for `backend.main`.

- [ ] **Step 3: Implement `backend/routers/entities.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Query
from backend import db, schemas

router = APIRouter()

SORTS = {
    "aum_desc": "estimated_aum_usd DESC NULLS LAST",
    "aum_asc": "estimated_aum_usd ASC NULLS LAST",
    "name": "name ASC",
    "data_quality_desc": "data_quality DESC",
}

@router.get("/api/entities", response_model=schemas.EntitiesPage)
def list_entities(
    country: str | None = None,
    region: str | None = None,
    type: str | None = None,
    sector: str | None = None,
    min_aum_usd: float | None = None,
    max_aum_usd: float | None = None,
    controlling_family: str | None = None,
    q: str | None = None,
    sort: str = "aum_desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    params: list = []
    if country:
        codes = [c.strip().upper() for c in country.split(",") if c.strip()]
        where.append(f"country IN ({','.join('?' * len(codes))})")
        params.extend(codes)
    if region:
        where.append("region = ?"); params.append(region)
    if type:
        types = [t.strip() for t in type.split(",") if t.strip()]
        where.append(f"type IN ({','.join('?' * len(types))})")
        params.extend(types)
    if sector:
        where.append("sectors LIKE ?"); params.append(f"%{sector}%")
    if min_aum_usd is not None:
        where.append("estimated_aum_usd >= ?"); params.append(min_aum_usd)
    if max_aum_usd is not None:
        where.append("estimated_aum_usd <= ?"); params.append(max_aum_usd)
    if controlling_family:
        where.append("controlling_family LIKE ?")
        params.append(f"%{controlling_family}%")
    if q:
        where.append("(name LIKE ? OR controlling_family LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = SORTS.get(sort, SORTS["aum_desc"]).replace(" NULLS LAST", "")
    # SQLite doesn't support NULLS LAST; emulate via CASE.
    if "estimated_aum_usd" in order_sql:
        order_sql = (
            "CASE WHEN estimated_aum_usd IS NULL THEN 1 ELSE 0 END, "
            + order_sql
        )

    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM entities {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM entities {where_sql} "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

    return {"total": total, "results": [dict(r) for r in rows]}
```

- [ ] **Step 4: Implement `backend/main.py`**

```python
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.routers import entities

app = FastAPI(title="Capital Agent")
app.include_router(entities.router)

STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/backend/test_entities.py -v
```

Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/routers/__init__.py backend/routers/entities.py tests/backend/
git commit -m "feat(backend): GET /api/entities with filters and pagination"
```

### Task 3.3: `GET /api/entities/{id}`

**Files:**
- Create: `backend/routers/entity.py`
- Create: `tests/backend/test_entity.py`

- [ ] **Step 1: Write the failing test**

```python
def test_detail_404(client):
    assert client.get("/api/entities/missing").status_code == 404

def test_detail_returns_entity(client):
    r = client.get("/api/entities/in-premji")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"]["name"] == "Premji Invest"
    assert body["sources"] == []
    assert body["activities"] == []
    assert body["assumptions"] == []
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/backend/test_entity.py -v
```

Expected: 404 returns wrong code or import errors.

- [ ] **Step 3: Implement `backend/routers/entity.py`**

```python
from fastapi import APIRouter, HTTPException
from backend import db, schemas

router = APIRouter()

@router.get("/api/entities/{entity_id}", response_model=schemas.EntityDetail)
def get_entity(entity_id: str):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        sources = [dict(r) for r in conn.execute(
            "SELECT field, source_type, url, note, retrieved_at "
            "FROM sources WHERE entity_id = ?", (entity_id,)
        ).fetchall()]
        activities = [dict(r) for r in conn.execute(
            "SELECT date, kind, description, source_url "
            "FROM activities WHERE entity_id = ? ORDER BY date DESC",
            (entity_id,)
        ).fetchall()]
        assumptions = [r[0] for r in conn.execute(
            "SELECT text FROM assumptions WHERE entity_id = ?", (entity_id,)
        ).fetchall()]

    return {
        "entity": dict(row),
        "sources": sources,
        "activities": activities,
        "assumptions": assumptions,
    }
```

- [ ] **Step 4: Wire into `backend/main.py`**

Edit `backend/main.py` to add:

```python
from backend.routers import entities, entity
app.include_router(entities.router)
app.include_router(entity.router)
```

(Replace the single existing `include_router` line.)

- [ ] **Step 5: Run tests**

```bash
pytest tests/backend/test_entity.py -v
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/entity.py backend/main.py tests/backend/test_entity.py
git commit -m "feat(backend): GET /api/entities/{id}"
```

### Task 3.4: `POST /api/ask` (LLM tool-use loop)

**Files:**
- Create: `backend/llm.py`
- Create: `backend/routers/ask.py`
- Create: `tests/backend/test_ask.py`

- [ ] **Step 1: Write the failing test (mocked OpenRouter)**

```python
import json
from unittest.mock import patch

def _fake_openrouter_two_step(messages, tools):
    """First call: return a tool_call for query_entities. Second call: return final text."""
    # Look for an existing tool result in messages → second turn
    if any(m.get("role") == "tool" for m in messages):
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "answer": "Two Indian SFOs match.",
                        "cited_entity_ids": ["in-premji"],
                    }),
                }
            }]
        }
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "query_entities",
                                 "arguments": json.dumps({"country": "IN", "type": "sfo"})}
                }]
            }
        }]
    }

def test_ask_calls_tool_then_returns_answer(client):
    with patch("backend.llm.chat_completion", side_effect=_fake_openrouter_two_step):
        r = client.post("/api/ask", json={"question": "Indian SFOs?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("Two Indian")
    assert body["filters_used"] == {"country": "IN", "type": "sfo"}
    ids = {e["id"] for e in body["entities"]}
    assert "in-premji" in ids
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/backend/test_ask.py -v
```

- [ ] **Step 3: Implement `backend/llm.py`**

```python
from __future__ import annotations

import os
import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "owl-alpha")

def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    payload: dict = {"model": MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 4: Implement `backend/routers/ask.py`**

```python
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from backend import db, llm, schemas
from backend.routers.entities import list_entities

router = APIRouter()

SYSTEM = (
    "You map natural-language questions about Asian family-office capital pools "
    "to a single tool call: query_entities(filters). After the tool returns "
    "matches, write a 2-3 sentence factual answer and a list of cited_entity_ids. "
    "Reply with strict JSON: {\"answer\": str, \"cited_entity_ids\": [str]}."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "query_entities",
        "description": "Filter the entities database. All filters AND-combined.",
        "parameters": {
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "region": {"type": "string"},
                "type": {"type": "string"},
                "sector": {"type": "string"},
                "min_aum_usd": {"type": "number"},
                "controlling_family": {"type": "string"},
                "q": {"type": "string"},
            },
        },
    },
}]

def _run_tool(args: dict) -> dict:
    page = list_entities(
        country=args.get("country"),
        region=args.get("region"),
        type=args.get("type"),
        sector=args.get("sector"),
        min_aum_usd=args.get("min_aum_usd"),
        controlling_family=args.get("controlling_family"),
        q=args.get("q"),
        sort="aum_desc", limit=50, offset=0,
    )
    return page

@router.post("/api/ask", response_model=schemas.AskResponse)
def ask(req: schemas.AskRequest):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": req.question},
    ]
    first = llm.chat_completion(messages, tools=TOOLS)
    msg = first["choices"][0]["message"]
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        raise HTTPException(status_code=502, detail="LLM did not call tool")

    tc = tool_calls[0]
    args = json.loads(tc["function"]["arguments"])
    tool_result = _run_tool(args)

    messages.extend([
        {"role": "assistant", "content": None, "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": tc["id"],
         "content": json.dumps({"matches": [
             {"id": e["id"], "name": e["name"], "country": e["country"],
              "estimated_aum_usd": e["estimated_aum_usd"]}
             for e in tool_result["results"]
         ]})},
    ])

    second = llm.chat_completion(messages)
    text = second["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    cited = set(parsed.get("cited_entity_ids", []))
    entities = [e for e in tool_result["results"] if e["id"] in cited]
    return {"answer": parsed.get("answer", ""), "entities": entities,
            "filters_used": args}
```

- [ ] **Step 5: Wire into `backend/main.py`**

```python
from backend.routers import entities, entity, ask
app.include_router(entities.router)
app.include_router(entity.router)
app.include_router(ask.router)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/backend/test_ask.py -v
```

Expected: 1 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/llm.py backend/routers/ask.py backend/main.py tests/backend/test_ask.py
git commit -m "feat(backend): POST /api/ask with LLM tool-use loop"
```

---

## Phase 4 — Frontend

### Task 4.1: Vite/React/Tailwind scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/theme.css`

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "capital-agent-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "lucide-react": "^0.451.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "vite": "^5.4.8"
  }
}
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
  build: { outDir: "dist" },
});
```

- [ ] **Step 3: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write `frontend/tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#020617", panel: "#0F172A", border: "#334155",
        muted: "#94A3B8", text: "#F8FAFC", accent: "#22C55E",
        elev: "#1A1E2F",
      },
      fontFamily: {
        sans: ["Fira Sans", "system-ui", "sans-serif"],
        mono: ["Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 5: Write `frontend/postcss.config.js`**

```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 6: Write `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Capital Agent</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600&family=Fira+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
  </head>
  <body class="bg-bg text-text">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Write `frontend/src/theme.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root { height: 100%; }
body { margin: 0; font-family: 'Fira Sans', system-ui, sans-serif; }
.numeric { font-family: 'Fira Code', monospace; font-variant-numeric: tabular-nums; }
:focus-visible { outline: 2px solid #22C55E; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
```

- [ ] **Step 8: Write `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./theme.css";

const qc = new QueryClient();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}><App /></QueryClientProvider>
  </React.StrictMode>
);
```

- [ ] **Step 9: Install and smoke test**

```bash
cd frontend && npm install && npm run build
```

Expected: `dist/` produced with no errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/vite.config.ts frontend/tsconfig.json \
        frontend/tailwind.config.ts frontend/postcss.config.js frontend/index.html \
        frontend/src/main.tsx frontend/src/theme.css
git add frontend/package-lock.json
git commit -m "chore(frontend): vite + react + tailwind scaffold"
```

### Task 4.2: API client + types

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`

- [ ] **Step 1: Write `frontend/src/types.ts`**

```ts
export interface Entity {
  id: string;
  name: string;
  type: string;
  country: string;
  region: string;
  controlling_family?: string | null;
  controllers?: string[] | null;
  ticker?: string | null;
  exchange?: string | null;
  estimated_aum_usd?: number | null;
  aum_basis?: string | null;
  ownership_pct?: number | null;
  sectors?: string[] | null;
  deployment?: string | null;
  accessibility?: string | null;
  thesis_blurb?: string | null;
  data_quality: number;
  updated_at: string;
}

export interface EntitiesPage { total: number; results: Entity[]; }

export interface EntityDetail {
  entity: Entity;
  sources: { field: string; source_type: string; url?: string | null;
             note?: string | null; retrieved_at: string }[];
  activities: { date?: string | null; kind: string; description: string;
                source_url?: string | null }[];
  assumptions: string[];
}

export interface AskResponse {
  answer: string;
  entities: Entity[];
  filters_used: Record<string, unknown>;
}

export interface Filters {
  country?: string;
  region?: string;
  type?: string;
  sector?: string;
  min_aum_usd?: number;
  controlling_family?: string;
  q?: string;
  sort?: "aum_desc" | "aum_asc" | "name" | "data_quality_desc";
  limit?: number;
  offset?: number;
}
```

- [ ] **Step 2: Write `frontend/src/api.ts`**

```ts
import type { EntitiesPage, EntityDetail, AskResponse, Filters } from "./types";

function qs(f: Filters): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  return p.toString();
}

export async function listEntities(f: Filters): Promise<EntitiesPage> {
  const r = await fetch(`/api/entities?${qs(f)}`);
  if (!r.ok) throw new Error(`entities ${r.status}`);
  return r.json();
}

export async function getEntity(id: string): Promise<EntityDetail> {
  const r = await fetch(`/api/entities/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error(`entity ${r.status}`);
  return r.json();
}

export async function ask(question: string): Promise<AskResponse> {
  const r = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!r.ok) throw new Error(`ask ${r.status}`);
  return r.json();
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat(frontend): typed API client"
```

### Task 4.3: Components

**Files:**
- Create: `frontend/src/components/TopBar.tsx`
- Create: `frontend/src/components/FilterPanel.tsx`
- Create: `frontend/src/components/EntityTable.tsx`
- Create: `frontend/src/components/AskPanel.tsx`
- Create: `frontend/src/components/DetailView.tsx`

- [ ] **Step 1: Write `frontend/src/components/TopBar.tsx`**

```tsx
import { Search } from "lucide-react";
import { useState } from "react";

interface Props { onAsk: (q: string) => void }

export default function TopBar({ onAsk }: Props) {
  const [q, setQ] = useState("");
  return (
    <header className="bg-panel border-b border-border px-4 py-3 flex items-center gap-3">
      <div className="text-accent font-mono font-bold">▲ CAPITAL.AGENT</div>
      <form
        className="flex-1 flex"
        onSubmit={(e) => { e.preventDefault(); if (q.trim()) onAsk(q); }}
      >
        <div className="flex-1 flex items-center bg-elev border border-border rounded-md px-3 py-2">
          <Search size={16} className="text-muted mr-2" aria-hidden />
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Ask about Asian family offices…"
            aria-label="Ask about Asian family offices"
            className="flex-1 bg-transparent outline-none text-text placeholder-muted text-sm"
          />
        </div>
      </form>
    </header>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/FilterPanel.tsx`**

```tsx
import type { Filters } from "../types";

const REGIONS: { code: string; label: string; countries: string[] }[] = [
  { code: "East Asia", label: "East Asia", countries: ["HK","JP","KR","CN","MN"] },
  { code: "SEA", label: "SEA", countries: ["SG","MY","ID","TH","PH","VN","KH","LA","MM","BN"] },
  { code: "South Asia", label: "South Asia", countries: ["IN","PK","LK","BD","NP","BT"] },
  { code: "Oceania", label: "Oceania", countries: ["AU","NZ"] },
  { code: "Central Asia", label: "Central Asia", countries: ["KZ"] },
];

const TYPES = ["listed_holding", "sfo", "mfo", "trust", "foundation"];

interface Props { value: Filters; onChange: (f: Filters) => void }

export default function FilterPanel({ value, onChange }: Props) {
  const selectedCountries = new Set((value.country ?? "").split(",").filter(Boolean));
  const toggleCountry = (c: string) => {
    const next = new Set(selectedCountries);
    next.has(c) ? next.delete(c) : next.add(c);
    onChange({ ...value, country: [...next].join(",") || undefined, offset: 0 });
  };
  const selectedTypes = new Set((value.type ?? "").split(",").filter(Boolean));
  const toggleType = (t: string) => {
    const next = new Set(selectedTypes);
    next.has(t) ? next.delete(t) : next.add(t);
    onChange({ ...value, type: [...next].join(",") || undefined, offset: 0 });
  };
  return (
    <aside className="w-56 bg-panel border-r border-border p-3 overflow-y-auto text-sm">
      {REGIONS.map((r) => (
        <section key={r.code} className="mb-4">
          <h3 className="text-muted text-xs uppercase tracking-wider mb-1">{r.label}</h3>
          {r.countries.map((c) => (
            <label key={c} className="flex items-center gap-2 py-0.5 cursor-pointer">
              <input type="checkbox" checked={selectedCountries.has(c)}
                     onChange={() => toggleCountry(c)} className="accent-accent" />
              <span className="font-mono text-xs">{c}</span>
            </label>
          ))}
        </section>
      ))}
      <section className="mb-4">
        <h3 className="text-muted text-xs uppercase tracking-wider mb-1">Type</h3>
        {TYPES.map((t) => (
          <label key={t} className="flex items-center gap-2 py-0.5 cursor-pointer">
            <input type="checkbox" checked={selectedTypes.has(t)}
                   onChange={() => toggleType(t)} className="accent-accent" />
            <span className="text-xs">{t.replace("_", " ")}</span>
          </label>
        ))}
      </section>
      <section>
        <h3 className="text-muted text-xs uppercase tracking-wider mb-1">Min AUM (USD)</h3>
        <input
          type="number" min={0} step={100_000_000}
          value={value.min_aum_usd ?? ""}
          onChange={(e) => onChange({
            ...value,
            min_aum_usd: e.target.value ? Number(e.target.value) : undefined,
            offset: 0,
          })}
          className="w-full bg-elev border border-border rounded px-2 py-1 font-mono text-xs text-accent"
          aria-label="Minimum AUM in USD"
        />
      </section>
    </aside>
  );
}
```

- [ ] **Step 3: Write `frontend/src/components/EntityTable.tsx`**

```tsx
import type { Entity } from "../types";

interface Props {
  entities: Entity[];
  total: number;
  onSelect: (id: string) => void;
  onSort: (s: "aum_desc" | "aum_asc" | "name" | "data_quality_desc") => void;
}

function fmtAum(v?: number | null): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function dqDots(n: number): string {
  return "●".repeat(n) + "○".repeat(5 - n);
}

export default function EntityTable({ entities, total, onSelect, onSort }: Props) {
  return (
    <div className="flex-1 overflow-auto">
      <div className="px-3 py-2 text-muted text-xs">{total} results</div>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-panel">
          <tr className="text-muted text-xs uppercase">
            <th className="text-left px-3 py-2 cursor-pointer"
                onClick={() => onSort("name")}>Name</th>
            <th className="text-left px-3 py-2">Country</th>
            <th className="text-left px-3 py-2">Type</th>
            <th className="text-left px-3 py-2">Family</th>
            <th className="text-right px-3 py-2 cursor-pointer"
                onClick={() => onSort("aum_desc")}>AUM</th>
            <th className="text-left px-3 py-2 cursor-pointer"
                onClick={() => onSort("data_quality_desc")}>DQ</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr key={e.id}
                className="border-b border-elev hover:bg-panel cursor-pointer"
                onClick={() => onSelect(e.id)}>
              <td className="px-3 py-2">{e.name}</td>
              <td className="px-3 py-2 font-mono text-muted">{e.country}</td>
              <td className="px-3 py-2 text-xs">{e.type}</td>
              <td className="px-3 py-2">{e.controlling_family ?? "—"}</td>
              <td className="px-3 py-2 numeric text-right text-accent">
                {fmtAum(e.estimated_aum_usd)}
              </td>
              <td className="px-3 py-2 numeric text-accent">
                {dqDots(e.data_quality)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/AskPanel.tsx`**

```tsx
import type { AskResponse } from "../types";
import { X } from "lucide-react";

interface Props { result: AskResponse; onDismiss: () => void; onSelect: (id: string) => void }

export default function AskPanel({ result, onDismiss, onSelect }: Props) {
  return (
    <section className="border-b border-border bg-panel p-4">
      <div className="flex justify-between gap-4">
        <p className="text-text">{result.answer}</p>
        <button onClick={onDismiss} aria-label="Dismiss answer"
                className="text-muted hover:text-text">
          <X size={16} />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {Object.entries(result.filters_used).map(([k, v]) => (
          <span key={k} className="bg-elev border border-border text-xs
                                   text-muted px-2 py-0.5 rounded font-mono">
            {k}: {String(v)}
          </span>
        ))}
      </div>
      {result.entities.length > 0 && (
        <ul className="mt-3 grid gap-1">
          {result.entities.map((e) => (
            <li key={e.id}>
              <button onClick={() => onSelect(e.id)}
                      className="text-accent hover:underline text-sm">
                {e.name} <span className="text-muted">({e.country})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Write `frontend/src/components/DetailView.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { getEntity } from "../api";

interface Props { id: string; onBack: () => void }

export default function DetailView({ id, onBack }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id], queryFn: () => getEntity(id),
  });
  if (isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (error || !data) return <div className="p-6 text-muted">Failed to load.</div>;
  const e = data.entity;
  return (
    <div className="flex-1 overflow-auto p-6">
      <button onClick={onBack}
              className="flex items-center gap-1 text-muted hover:text-text mb-4">
        <ArrowLeft size={14} /> Back
      </button>
      <h2 className="text-2xl font-semibold">{e.name}</h2>
      <p className="text-muted">{e.country} · {e.type} · {e.controlling_family}</p>
      <p className="numeric text-accent text-xl mt-2">
        ${e.estimated_aum_usd?.toLocaleString() ?? "—"}
        <span className="text-muted text-xs ml-2">{e.aum_basis}</span>
      </p>
      {e.thesis_blurb && <p className="mt-4">{e.thesis_blurb}</p>}

      <h3 className="mt-6 text-muted uppercase text-xs tracking-wider">Sources</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {data.sources.map((s, i) => (
          <li key={i}>
            <span className="font-mono text-xs text-muted">{s.field}</span> ·{" "}
            <span className="text-xs">{s.source_type}</span>
            {s.url && <> · <a href={s.url} className="text-accent hover:underline"
                              target="_blank" rel="noreferrer">link</a></>}
            {s.note && <div className="text-muted text-xs">{s.note}</div>}
          </li>
        ))}
      </ul>

      {data.activities.length > 0 && (
        <>
          <h3 className="mt-6 text-muted uppercase text-xs tracking-wider">Activity</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {data.activities.map((a, i) => (
              <li key={i}>
                <span className="font-mono text-xs text-muted">{a.date ?? "—"}</span> ·{" "}
                <span className="text-xs">{a.kind}</span> — {a.description}
              </li>
            ))}
          </ul>
        </>
      )}

      {data.assumptions.length > 0 && (
        <>
          <h3 className="mt-6 text-muted uppercase text-xs tracking-wider">Assumptions</h3>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {data.assumptions.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/
git commit -m "feat(frontend): top bar, filters, table, ask panel, detail view"
```

### Task 4.4: App shell

**Files:**
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import TopBar from "./components/TopBar";
import FilterPanel from "./components/FilterPanel";
import EntityTable from "./components/EntityTable";
import AskPanel from "./components/AskPanel";
import DetailView from "./components/DetailView";
import { listEntities, ask } from "./api";
import type { AskResponse, Filters } from "./types";

export default function App() {
  const [filters, setFilters] = useState<Filters>({ sort: "aum_desc", limit: 50, offset: 0 });
  const [askResult, setAskResult] = useState<AskResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [askLoading, setAskLoading] = useState(false);

  const { data } = useQuery({
    queryKey: ["entities", filters],
    queryFn: () => listEntities(filters),
    placeholderData: (prev) => prev,
  });

  const handleAsk = async (q: string) => {
    setAskLoading(true);
    try { setAskResult(await ask(q)); }
    catch { setAskResult({ answer: "Sorry — the assistant is unreachable.",
                            entities: [], filters_used: {} }); }
    finally { setAskLoading(false); }
  };

  return (
    <div className="h-full flex flex-col">
      <TopBar onAsk={handleAsk} />
      <div className="flex-1 flex overflow-hidden">
        <FilterPanel value={filters} onChange={setFilters} />
        {selected ? (
          <DetailView id={selected} onBack={() => setSelected(null)} />
        ) : (
          <main className="flex-1 flex flex-col overflow-hidden">
            {askLoading && <div className="px-4 py-2 text-muted text-sm">Thinking…</div>}
            {askResult && (
              <AskPanel result={askResult}
                        onDismiss={() => setAskResult(null)}
                        onSelect={setSelected} />
            )}
            <EntityTable
              entities={data?.results ?? []}
              total={data?.total ?? 0}
              onSelect={setSelected}
              onSort={(s) => setFilters({ ...filters, sort: s, offset: 0 })}
            />
          </main>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build to verify it compiles**

```bash
cd frontend && npm run build
```

Expected: `dist/` produced, no TS errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): App shell wires TopBar/Filters/Table/Ask/Detail"
```

---

## Phase 5 — Container & deployment

### Task 5.1: Cert + entrypoint scripts

**Files:**
- Create: `scripts/gen-cert.sh`
- Create: `scripts/entrypoint.sh`

- [ ] **Step 1: Write `scripts/gen-cert.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout /app/certs/key.pem -out /app/certs/cert.pem \
  -subj "/CN=localhost" -days 365 \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 /app/certs/key.pem
```

- [ ] **Step 2: Write `scripts/entrypoint.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/data
if [[ ! -s /app/data/capital.db ]]; then
  echo "[entrypoint] seeding /app/data/capital.db from image"
  cp /app/seed/capital.db /app/data/capital.db
fi
export DB_PATH=/app/data/capital.db
exec "$@"
```

- [ ] **Step 3: Make executable, commit**

```bash
chmod +x scripts/gen-cert.sh scripts/entrypoint.sh
git add scripts/
git commit -m "chore(scripts): cert generator + entrypoint with seed copy"
```

### Task 5.2: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Write the Dockerfile** (mirrors §8 of the spec)

```dockerfile
# Stage 1: Frontend build
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Ingestion (produces seed DB inside the image)
FROM python:3.12-slim AS ingest
WORKDIR /ingest
COPY ingest/ ./ingest/
COPY requirements-ingest.txt .
RUN pip install --no-cache-dir -r requirements-ingest.txt
ARG POLYGON_API_KEY=""
ARG FINNHUB_API_KEY=""
ARG ALPHAVANTAGE_API_KEY=""
ARG OPENROUTER_API_KEY=""
ARG ENRICH=""
ENV POLYGON_API_KEY=$POLYGON_API_KEY \
    FINNHUB_API_KEY=$FINNHUB_API_KEY \
    ALPHAVANTAGE_API_KEY=$ALPHAVANTAGE_API_KEY \
    OPENROUTER_API_KEY=$OPENROUTER_API_KEY
RUN python -m ingest.run --out /capital.db ${ENRICH:+--enrich}

# Stage 3: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-ingest.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ingest.txt
COPY backend/ ./backend/
COPY ingest/ ./ingest/
COPY scripts/gen-cert.sh scripts/entrypoint.sh ./
RUN chmod +x ./gen-cert.sh ./entrypoint.sh && ./gen-cert.sh
COPY --from=frontend /fe/dist ./backend/static
COPY --from=ingest /capital.db /app/seed/capital.db
VOLUME /app/data
EXPOSE 8443
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/certs/key.pem", \
     "--ssl-certfile", "/app/certs/cert.pem"]
```

- [ ] **Step 2: Build the image**

```bash
docker build \
  --build-arg POLYGON_API_KEY=$POLYGON_API_KEY \
  --build-arg FINNHUB_API_KEY=$FINNHUB_API_KEY \
  --build-arg ALPHAVANTAGE_API_KEY=$ALPHAVANTAGE_API_KEY \
  -t capital-agent .
```

Expected: build completes; `[write] N entities -> /capital.db` appears in stage 2 logs with N ≥ 50.

- [ ] **Step 3: Smoke run + manual check**

```bash
docker run -d --name capital-agent \
  -p 8443:8443 \
  -v capital-data:/app/data \
  -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  capital-agent
sleep 2
curl -k https://localhost:8443/api/entities?limit=3 | head -c 400
docker logs capital-agent | tail -20
```

Expected: JSON body with `total` and 3 results. Browser at `https://localhost:8443` (accept self-signed warning) shows the dark UI with the table populated.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "chore: multi-stage Dockerfile (frontend → ingest → runtime)"
```

### Task 5.3: Refresh path verification

- [ ] **Step 1: Refresh inside the running container**

```bash
docker exec -e POLYGON_API_KEY=$POLYGON_API_KEY \
            -e FINNHUB_API_KEY=$FINNHUB_API_KEY \
            -e ALPHAVANTAGE_API_KEY=$ALPHAVANTAGE_API_KEY \
            capital-agent python -m ingest.run --out /app/data/capital.db
curl -k https://localhost:8443/api/entities?limit=1
```

Expected: refresh logs print, then a fresh JSON entity result without restarting the container.

---

## Phase 6 — Documentation

### Task 6.1: `docs/DATA.md`

**Files:**
- Create: `docs/DATA.md`

- [ ] **Step 1: Write the data dictionary**

````markdown
# Data Dictionary — `capital.db`

SQLite database produced by `ingest/run.py`. Four tables; flat on purpose.

## `entities` — one row per capital pool

| Column | Type | Meaning | Example |
|---|---|---|---|
| `id` | TEXT PK | Stable slug | `hk-cheung-kong-holdings` |
| `name` | TEXT | Entity name as known publicly | `Cheung Kong Holdings` |
| `type` | TEXT | One of `listed_holding` / `sfo` / `mfo` / `trust` / `foundation` | `sfo` |
| `country` | TEXT | ISO 3166-1 alpha-2 | `HK` |
| `region` | TEXT | `East Asia` / `SEA` / `South Asia` / `Oceania` / `Central Asia` | `East Asia` |
| `controlling_family` | TEXT | Family surname / dynasty | `Li` |
| `controllers` | JSON array | Named individuals influencing capital allocation | `["Li Ka-shing"]` |
| `ticker`, `exchange` | TEXT | Listed entities only | `0001.HK`, `HKEX` |
| `estimated_aum_usd` | REAL | Best estimate of allocatable capital, USD | `28400000000` |
| `aum_basis` | TEXT | `disclosed` / `market_cap` / `estimate` / `unknown` | `market_cap` |
| `ownership_pct` | REAL | Family ownership of listed vehicle | `43.0` |
| `sectors` | JSON array | Sector tags | `["telecom","infra"]` |
| `deployment` | TEXT | `direct` / `external_managers` / `mixed` / `unknown` | `mixed` |
| `accessibility` | TEXT | `open` / `restricted` / `closed` / `unknown` | `restricted` |
| `thesis_blurb` | TEXT | LLM-generated 1–2 sentence summary | _generated_ |
| `data_quality` | INTEGER (1–5) | See rubric below | `4` |
| `updated_at` | TEXT (ISO) | When this row was written | `2026-05-15T00:00:00Z` |

## `sources` — provenance

Every material claim about an entity has a row here.

| Column | Meaning |
|---|---|
| `entity_id` | FK → `entities.id` |
| `field` | Which entity column the source backs |
| `source_type` | `mcp:polygon` / `mcp:finnhub` / `mcp:alphavantage` / `filing` / `news` / `curated` / `llm:openrouter` |
| `url` | Link if available |
| `note` | Free-text context |
| `retrieved_at` | ISO timestamp |

## `activities` — recent investment activity

| Column | Meaning |
|---|---|
| `entity_id` | FK |
| `date` | YYYY-MM-DD |
| `kind` | `deal` / `exit` / `fund_commitment` / `allocation_change` |
| `description` | What happened |
| `source_url` | Link if available |

## `assumptions` — explicit estimation logic

Each row is one assumption used to derive an estimated field. Surfaced verbatim in the detail view.

## Data-quality rubric (1–5)

- **5** — disclosed AUM + named controllers + sourced activity in last 24 months
- **4** — market-cap-derived AUM + named controllers + sourced activity
- **3** — market-cap or estimated AUM + family identifier (no individuals) OR vice versa
- **2** — estimated AUM + family identifier only, no recent activity
- **1** — placeholder; AUM unknown
````

- [ ] **Step 2: Commit**

```bash
git add docs/DATA.md
git commit -m "docs: data dictionary"
```

### Task 6.2: `docs/METHODOLOGY.md`

**Files:**
- Create: `docs/METHODOLOGY.md`

- [ ] **Step 1: Write methodology**

````markdown
# Methodology

## Goal
Produce a defensible, repeatable inventory of family-office and family-controlled capital pools across 22 Asian markets.

## Two-track discovery

**Listed entities (Tier 1 + 2 countries).** For each country, fetch top companies by market cap via MCP servers (Finnhub primary, Polygon fallback). For each, fetch the top-10 holders. An entity is classified family-controlled if any holder either (a) matches a known-family entry in `ingest/seeds/known_families.yaml` for that country, or (b) holds ≥25% AND is a personal name (not Inc/Corp/Trust Co/Bank/Fund/etc., per regex in `ingest/classify.py::is_family_holder`).

**Curated private offices (all tiers).** `ingest/seeds/private_offices.yaml` lists known SFOs/MFOs/foundations with a `source_url` and a `note` explaining the AUM basis for each entry.

The two tracks are merged with dedupe on `(country, controlling_family)` — curated entries win.

## Tiering

- **Tier 1** (HK, JP, SG, IN, KR, AU, CN): full listed loop + seed.
- **Tier 2** (MY, ID, TH, PH, NZ, VN): listed where MCP supports the exchange + seed.
- **Tier 3** (Myanmar, Laos, Bhutan, Brunei, Mongolia, Pakistan, Sri Lanka, Bangladesh, Nepal, Cambodia, Kazakhstan): seed only.

## Provenance

Every material field write also writes a `sources` row. Estimated AUM also requires an `assumptions` row when the basis is `estimate`. Curated rows must include `source_url` and `note`.

## Data quality scoring

Computed by `ingest/classify.py::infer_data_quality`. See `docs/DATA.md` for the rubric.

## Failure handling

- MCP unreachable for a country → skip, log, build continues.
- LLM enrichment failure → entity written with `thesis_blurb` null.
- Whole-build sanity check: ingestion fails if final entity count < 50.

## Refresh

The pipeline is idempotent. Re-run with:

```
docker exec capital-agent python -m ingest.run --out /app/data/capital.db [--enrich]
```

Backend reads continue uninterrupted thanks to SQLite WAL mode.

## Limits

- Polygon's free tier does not expose holder data; classification leans on Finnhub.
- Finnhub does not cover every Asian exchange; Tier-3 countries rely entirely on the seed list.
- Frontier-market depth is explicitly low — entities for those countries are placeholders to ensure regional coverage rather than triage-grade data.
````

- [ ] **Step 2: Commit**

```bash
git add docs/METHODOLOGY.md
git commit -m "docs: methodology"
```

### Task 6.3: Flesh out `README.md`

- [ ] **Step 1: Replace `README.md`**

````markdown
# Family Office Capital Agent

A single-container web app that surfaces family-office and family-controlled capital pools across Asia. Bloomberg-style dense data table, region/country/AUM filters, and a natural-language ask endpoint.

See:
- `docs/superpowers/specs/2026-05-15-family-office-capital-agent-design.md` — design
- `docs/DATA.md` — data dictionary
- `docs/METHODOLOGY.md` — how the dataset is built

## Quick start (Docker)

```bash
docker build \
  --build-arg POLYGON_API_KEY=$POLYGON_API_KEY \
  --build-arg FINNHUB_API_KEY=$FINNHUB_API_KEY \
  --build-arg ALPHAVANTAGE_API_KEY=$ALPHAVANTAGE_API_KEY \
  -t capital-agent .

docker run -d --name capital-agent \
  -p 8443:8443 \
  -v capital-data:/app/data \
  -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  -e POLYGON_API_KEY=$POLYGON_API_KEY \
  -e FINNHUB_API_KEY=$FINNHUB_API_KEY \
  -e ALPHAVANTAGE_API_KEY=$ALPHAVANTAGE_API_KEY \
  capital-agent

open https://localhost:8443  # accept the self-signed cert warning
```

## Refresh the dataset

```bash
docker exec capital-agent python -m ingest.run --out /app/data/capital.db [--enrich]
```

Backend keeps serving during the refresh (SQLite WAL mode).

## Local dev

```bash
make ingest                    # produce data/capital.db
make backend                   # FastAPI on :8000
make frontend                  # Vite dev server on :5173, proxies /api → :8000
make test                      # pytest
```

## Endpoints

- `GET /api/entities` — filter / browse
- `GET /api/entities/{id}` — detail
- `POST /api/ask` — natural-language tool-use loop
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: full README"
```

---

## Verification

Run end-to-end:

1. `make test` — all backend + ingest tests pass.
2. `docker build … -t capital-agent .` — image builds; stage 2 logs report ≥50 entities.
3. `docker run …` then `curl -k https://localhost:8443/api/entities?limit=3` returns valid JSON.
4. Open `https://localhost:8443` in a browser:
   - Filter sidebar toggles country/type checkboxes; table updates.
   - Click a row → detail view shows sources/activities/assumptions.
   - Type a question in the top bar → answer + filters_used chips + cited entities render.
5. `docker exec capital-agent python -m ingest.run --out /app/data/capital.db` succeeds; subsequent API call reflects fresh `updated_at`.
6. Stop and restart the container with the same volume — data persists; entrypoint does not overwrite refreshed DB.

## Self-Review Notes

- **Spec coverage:** Each spec section maps to ≥1 task: §3 architecture → Phase 0/3/5; §4 data model → Task 1.1; §5 ingestion → Phase 1+2; §6 backend → Phase 3; §7 frontend → Phase 4; §8 container → Phase 5; §9 layout produced throughout; §10 testing covered in 1.1, 1.2, 3.2, 3.3, 3.4; §11 deliverables map → DATA.md/METHODOLOGY.md/README.md (Phase 6); §12 open items unchanged.
- **Type consistency:** `Entity` dataclass (ingest) and `Entity` pydantic model (backend) and `Entity` TS interface (frontend) all share the same column set; JSON columns (`controllers`, `sectors`) are list-typed at all three layers and (de)serialized in `write_db._entity_row` and `schemas.Entity._parse_json`.
- **Placeholder check:** Every code step has complete, runnable code. Seed YAML expects expansion to ≥50 entries — explicit instruction in Task 1.3 and reinforced by sanity check in Task 2.3.
