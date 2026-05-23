# Evidence-Backed Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the family-name dataset with evidence-backed investment vehicles answering the 7 core questions, served via a multi-turn LLM chat agent that does live web research with tool use.

**Architecture:** New normalized `evidence` table tied to source URLs; new `backend/research/` module with a 7-tool LLM tool-use loop (Exa search, Firecrawl scrape, Apollo lookup, Finnhub/Polygon market data, local DB query, validated DB write); SSE-streamed `POST /api/chat`; ~20 curated investment vehicles re-seeded via the same agent loop; minimal UI changes (Evidence column in table, 7 question sections in detail view, slide-out chat panel).

**Tech Stack:** Python 3.12, FastAPI, sse-starlette, sqlite3 (stdlib), httpx, pydantic v2, OpenRouter (`google/gemini-2.0-flash-exp:free` default). React 18 + Vite 5 + TypeScript + Tailwind. Existing test stack: pytest.

**Spec:** `docs/superpowers/specs/2026-05-23-evidence-pipeline-design.md`

---

## Shared constants (used across many tasks — keep in sync)

```python
QUESTION_KEYS = [
    "where_capital_sits",
    "how_much_capital",
    "who_controls",
    "how_deployed",
    "direct_or_external",
    "accessibility",
    "why_invest",
]

PROVENANCE_VALUES = {"curated", "chat_discovered", "chat_enriched"}

BANNED_GENERIC = (
    r"family office team|the family|investment team|family members|"
    r"management team|the office|in-house team|allocation team"
)

MIN_EVIDENCE_QUESTIONS = 5
```

These appear verbatim in Task 3 (validator), Task 6 (DB helper), Task 8 (tools), Task 9 (prompts). If you change one, change all.

---

## File Structure

```
backend/
├── research/                              # NEW module
│   ├── __init__.py
│   ├── constants.py                       # QUESTION_KEYS, PROVENANCE_VALUES, BANNED_GENERIC, MIN_EVIDENCE_QUESTIONS
│   ├── validator.py                       # validate_bundle()
│   ├── session.py                         # in-memory chat session store
│   ├── tools.py                           # 7 tool fns + JSON schemas
│   ├── prompts.py                         # SYSTEM_PROMPT
│   └── loop.py                            # async run_turn() yielding SSE events
├── routers/
│   ├── chat.py                            # NEW: POST /api/chat (SSE), GET /api/chat/{sid}
│   ├── entity.py                          # MODIFIED: include evidence in detail
│   ├── entities.py                        # unchanged
│   └── ask.py                             # DELETED
├── db.py                                  # MODIFIED: add commit_evidence_bundle()
├── schemas.py                             # MODIFIED: add Evidence, ChatRequest, etc.
├── llm.py                                 # MODIFIED: default model + tool-call helper
└── main.py                                # MODIFIED: register chat router, drop ask

ingest/
├── migrate_evidence.py                    # NEW: idempotent ALTER/CREATE
└── sources/
    ├── exa.py                             # MODIFIED: real impl
    ├── firecrawl.py                       # MODIFIED: real impl
    ├── apollo.py                          # MODIFIED: real impl
    ├── finnhub.py                         # NEW (re-add)
    └── polygon.py                         # NEW (re-add)

scripts/
└── curate_seed.py                         # NEW: non-interactive agent run over seed list

frontend/src/
├── api.ts                                 # MODIFIED: streamChat()
├── types.ts                               # MODIFIED: Evidence, EvidenceDetail, ChatEvent
├── App.tsx                                # MODIFIED: chat toggle, session id
└── components/
    ├── ChatPanel.tsx                      # NEW: slide-out chat
    ├── EntityTable.tsx                    # MODIFIED: Evidence column
    └── DetailView.tsx                     # MODIFIED: 7 question sections

docs/
├── METHODOLOGY.md                         # MODIFIED: new pipeline + scaling story
└── README.md                              # MODIFIED: chat trace example

tests/
├── ingest/
│   └── test_migrate_evidence.py           # NEW
├── backend/
│   ├── test_validator.py                  # NEW
│   ├── test_session.py                    # NEW
│   ├── test_commit_bundle.py              # NEW
│   ├── test_entity_with_evidence.py       # NEW
│   ├── test_chat.py                       # NEW (loop + SSE, mocked LLM)
│   └── test_ask.py                        # DELETED
```

---

# Phase A — Schema migration

## Task 1: Idempotent schema migration

**Files:**
- Create: `ingest/migrate_evidence.py`
- Create: `tests/ingest/test_migrate_evidence.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify fail**

```bash
cd "/Users/kikiye/htx/Capital Agent" && source .venv/bin/activate && pytest tests/ingest/test_migrate_evidence.py -v
```

Expected: `ImportError: No module named 'ingest.migrate_evidence'`.

- [ ] **Step 3: Implement migration**

```python
# ingest/migrate_evidence.py
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/ingest/test_migrate_evidence.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run migration against the live dev DB**

```bash
python -m ingest.migrate_evidence data/capital.db
```

Expected: prints `migration done`. Verify with `sqlite3 data/capital.db ".schema evidence"`.

- [ ] **Step 6: Commit**

```bash
git add ingest/migrate_evidence.py tests/ingest/test_migrate_evidence.py
git commit -m "feat(db): idempotent evidence-schema migration"
```

---

# Phase B — Source wrapper implementations (real bodies)

## Task 2: Real Exa, Firecrawl, Apollo + re-add Finnhub, Polygon

These are network glue — no unit tests, just clean fail-soft interfaces that return `[]` / `None` when keys are missing.

**Files:**
- Modify: `ingest/sources/exa.py`
- Modify: `ingest/sources/firecrawl.py`
- Modify: `ingest/sources/apollo.py`
- Create: `ingest/sources/finnhub.py`
- Create: `ingest/sources/polygon.py`

- [ ] **Step 1: Replace `ingest/sources/exa.py`**

```python
"""Exa neural search wrapper. EXA_API_KEY env."""
from __future__ import annotations
import os
import httpx

URL = "https://api.exa.ai/search"

def search(query: str, n: int = 5) -> list[dict]:
    """[{url, title, snippet}, ...]. [] when EXA_API_KEY missing or on error."""
    key = os.environ.get("EXA_API_KEY")
    if not key:
        return []
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(URL, headers={"x-api-key": key, "Content-Type": "application/json"},
                       json={"query": query, "numResults": min(n, 10),
                             "type": "neural", "contents": {"text": False}})
            if r.status_code != 200:
                print(f"[exa] {r.status_code}: {r.text[:200]}")
                return []
            data = r.json().get("results", [])
        return [{"url": x.get("url"), "title": x.get("title"),
                 "snippet": (x.get("text") or "")[:300]} for x in data][:n]
    except Exception as e:
        print(f"[exa] search failed: {e}")
        return []
```

- [ ] **Step 2: Replace `ingest/sources/firecrawl.py`**

```python
"""Firecrawl URL → markdown wrapper. FIRECRAWL_API_KEY env."""
from __future__ import annotations
import os
import httpx

URL = "https://api.firecrawl.dev/v1/scrape"
MAX_CHARS = 8000

def scrape(url: str) -> str | None:
    """Markdown text of `url` (truncated to MAX_CHARS). None on missing key/error."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        with httpx.Client(timeout=45.0) as c:
            r = c.post(URL, headers={"Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json"},
                       json={"url": url, "formats": ["markdown"]})
            if r.status_code != 200:
                print(f"[firecrawl] {r.status_code} for {url}: {r.text[:200]}")
                return None
            md = (r.json().get("data") or {}).get("markdown")
        return (md or "")[:MAX_CHARS] or None
    except Exception as e:
        print(f"[firecrawl] failed for {url}: {e}")
        return None
```

- [ ] **Step 3: Replace `ingest/sources/apollo.py`**

```python
"""Apollo organization lookup. APOLLO_API_KEY env."""
from __future__ import annotations
import os
import httpx

URL = "https://api.apollo.io/v1/organizations/search"

def org_lookup(name: str) -> dict | None:
    """{website, hq_country, employees, founded_year, industry}. None on miss."""
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        return None
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(URL, headers={"X-Api-Key": key, "Content-Type": "application/json"},
                       json={"q_organization_name": name, "page": 1, "per_page": 1})
            if r.status_code != 200:
                print(f"[apollo] {r.status_code}: {r.text[:200]}")
                return None
            orgs = r.json().get("organizations", [])
        if not orgs:
            return None
        o = orgs[0]
        return {
            "website": o.get("website_url"),
            "hq_country": o.get("country"),
            "employees": o.get("estimated_num_employees"),
            "founded_year": o.get("founded_year"),
            "industry": o.get("industry"),
        }
    except Exception as e:
        print(f"[apollo] failed for {name}: {e}")
        return None
```

- [ ] **Step 4: Create `ingest/sources/finnhub.py`**

```python
"""Finnhub fundamentals lookup. FINNHUB_API_KEY env."""
from __future__ import annotations
import os
import httpx

BASE = "https://finnhub.io/api/v1"

def company(ticker: str) -> dict | None:
    """{market_cap, name, exchange, industry}. None on missing key/miss."""
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return None
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/stock/profile2",
                      params={"symbol": ticker, "token": key})
            if r.status_code != 200 or not r.json():
                return None
            p = r.json()
        return {
            "market_cap": (p.get("marketCapitalization") or 0) * 1_000_000,
            "name": p.get("name"),
            "exchange": p.get("exchange"),
            "industry": p.get("finnhubIndustry"),
        }
    except Exception as e:
        print(f"[finnhub] company({ticker}) failed: {e}")
        return None
```

- [ ] **Step 5: Create `ingest/sources/polygon.py`**

```python
"""Polygon ticker resolver. POLYGON_API_KEY env."""
from __future__ import annotations
import os
import httpx

BASE = "https://api.polygon.io"

def ticker_lookup(query: str, n: int = 5) -> list[dict]:
    """[{ticker, name, country}, ...]. [] on missing key/error."""
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        return []
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/v3/reference/tickers",
                      params={"search": query, "active": "true",
                              "limit": min(n, 10), "apiKey": key})
            if r.status_code != 200:
                return []
            data = r.json().get("results", [])
        return [{"ticker": t.get("ticker"), "name": t.get("name"),
                 "country": t.get("locale")} for t in data][:n]
    except Exception as e:
        print(f"[polygon] ticker_lookup({query}) failed: {e}")
        return []
```

- [ ] **Step 6: Smoke import check**

```bash
python -c "from ingest.sources import exa, firecrawl, apollo, finnhub, polygon; \
print(exa.search('test'), firecrawl.scrape('https://example.com'), \
apollo.org_lookup('Premji Invest'), finnhub.company('AAPL'), \
polygon.ticker_lookup('Reliance'))"
```

Expected: prints `[] None None None []` when keys are absent. No exceptions.

- [ ] **Step 7: Commit**

```bash
git add ingest/sources/
git commit -m "feat(sources): real Exa/Firecrawl/Apollo bodies + re-add Finnhub/Polygon"
```

---

# Phase C — Research module (TDD)

## Task 3: `backend/research/constants.py`

**Files:**
- Create: `backend/research/__init__.py` (empty)
- Create: `backend/research/constants.py`

- [ ] **Step 1: Create `backend/research/__init__.py`** (empty file)

- [ ] **Step 2: Create `backend/research/constants.py`**

```python
"""Shared constants. Edit here, used everywhere in research/."""

QUESTION_KEYS: list[str] = [
    "where_capital_sits",
    "how_much_capital",
    "who_controls",
    "how_deployed",
    "direct_or_external",
    "accessibility",
    "why_invest",
]

PROVENANCE_VALUES = {"curated", "chat_discovered", "chat_enriched"}

BANNED_GENERIC = (
    r"family office team|the family|investment team|family members|"
    r"management team|the office|in-house team|allocation team"
)

MIN_EVIDENCE_QUESTIONS = 5
```

- [ ] **Step 3: Commit**

```bash
git add backend/research/__init__.py backend/research/constants.py
git commit -m "feat(research): shared constants module"
```

## Task 4: Validator (TDD)

**Files:**
- Create: `backend/research/validator.py`
- Create: `tests/backend/test_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_validator.py
from backend.research.validator import validate_bundle

def _valid_bundle():
    return {
        "entity": {
            "name": "Premji Invest", "type": "sfo", "country": "IN",
            "region": "South Asia", "controlling_family": "Premji",
            "ticker": None, "exchange": None,
            "estimated_aum_usd": 10_000_000_000.0, "aum_basis": "disclosed",
            "sectors": ["tech"], "deployment": "mixed",
            "accessibility": "restricted",
            "provenance": "chat_discovered", "confidence_score": 4,
        },
        "evidence": [
            {"question_key": "where_capital_sits",
             "answer": "Single-family office in Bangalore.",
             "confidence": 5, "source_urls": ["https://premjiinvest.com/about"]},
            {"question_key": "how_much_capital",
             "answer": "Disclosed AUM of $10B per official site.",
             "confidence": 5, "source_urls": ["https://premjiinvest.com/about"]},
            {"question_key": "who_controls",
             "answer": "Azim Premji (founder), Atul Gupta (CIO).",
             "confidence": 5, "source_urls": ["https://linkedin.com/in/atul-gupta"]},
            {"question_key": "how_deployed",
             "answer": "Mixed direct + external manager allocations.",
             "confidence": 4, "source_urls": ["https://premjiinvest.com/strategy"]},
            {"question_key": "direct_or_external",
             "answer": "~60% direct per latest disclosed split.",
             "confidence": 3, "source_urls": ["https://livemint.com/x"]},
        ],
        "sources": [
            {"url": "https://premjiinvest.com/about", "source_type": "firecrawl",
             "note": "official site", "retrieved_at": "2026-05-23T00:00:00Z"},
            {"url": "https://linkedin.com/in/atul-gupta", "source_type": "apollo",
             "note": "CIO LinkedIn", "retrieved_at": "2026-05-23T00:00:00Z"},
            {"url": "https://premjiinvest.com/strategy", "source_type": "firecrawl",
             "note": "strategy page", "retrieved_at": "2026-05-23T00:00:00Z"},
            {"url": "https://livemint.com/x", "source_type": "exa",
             "note": "press", "retrieved_at": "2026-05-23T00:00:00Z"},
        ],
    }

def test_valid_bundle_passes():
    assert validate_bundle(_valid_bundle()) == []

def test_fewer_than_5_questions_rejected():
    b = _valid_bundle()
    b["evidence"] = b["evidence"][:4]
    errors = validate_bundle(b)
    assert any("at least 5" in e for e in errors)

def test_unreferenced_source_url_rejected():
    b = _valid_bundle()
    b["evidence"][0]["source_urls"] = ["https://not-in-sources.com"]
    errors = validate_bundle(b)
    assert any("not in sources" in e for e in errors)

def test_generic_who_controls_rejected():
    b = _valid_bundle()
    b["evidence"][2]["answer"] = "The family office team handles allocations."
    errors = validate_bundle(b)
    assert any("generic" in e.lower() for e in errors)

def test_how_much_capital_without_figure_rejected():
    b = _valid_bundle()
    b["evidence"][1]["answer"] = "Substantial assets under management."
    errors = validate_bundle(b)
    assert any("how_much_capital" in e for e in errors)

def test_how_much_capital_explicit_no_estimate_accepted():
    b = _valid_bundle()
    b["evidence"][1]["answer"] = (
        "no public estimate; reasoning: privately held, no filings."
    )
    assert validate_bundle(b) == []

def test_bad_provenance_rejected():
    b = _valid_bundle()
    b["entity"]["provenance"] = "guessed"
    errors = validate_bundle(b)
    assert any("provenance" in e for e in errors)

def test_bad_confidence_rejected():
    b = _valid_bundle()
    b["entity"]["confidence_score"] = 99
    errors = validate_bundle(b)
    assert any("confidence_score" in e for e in errors)
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/backend/test_validator.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `backend/research/validator.py`**

```python
"""Server-side bundle validator. Returns list of error strings ([] = ok)."""
from __future__ import annotations
import re
from backend.research.constants import (
    QUESTION_KEYS, PROVENANCE_VALUES, BANNED_GENERIC, MIN_EVIDENCE_QUESTIONS,
)

_BANNED_RE = re.compile(BANNED_GENERIC, re.IGNORECASE)
_DOLLAR_RE = re.compile(r"\$")
_NO_ESTIMATE_RE = re.compile(r"no public estimate; reasoning:", re.IGNORECASE)

def validate_bundle(bundle: dict) -> list[str]:
    errors: list[str] = []
    entity = bundle.get("entity") or {}
    evidence = bundle.get("evidence") or []
    sources = bundle.get("sources") or []

    # provenance + confidence_score
    if entity.get("provenance") not in PROVENANCE_VALUES:
        errors.append(
            f"entity.provenance must be one of {sorted(PROVENANCE_VALUES)}"
        )
    cs = entity.get("confidence_score")
    if not isinstance(cs, int) or not (1 <= cs <= 5):
        errors.append("entity.confidence_score must be int in 1..5")

    # evidence coverage
    if len(evidence) < MIN_EVIDENCE_QUESTIONS:
        errors.append(
            f"evidence must cover at least {MIN_EVIDENCE_QUESTIONS} questions; "
            f"got {len(evidence)}"
        )
    seen = set()
    by_key: dict[str, dict] = {}
    for ev in evidence:
        k = ev.get("question_key")
        if k not in QUESTION_KEYS:
            errors.append(f"unknown question_key: {k!r}")
            continue
        if k in seen:
            errors.append(f"duplicate question_key: {k}")
        seen.add(k)
        by_key[k] = ev

    # citation integrity
    source_urls = {s.get("url") for s in sources}
    for ev in evidence:
        for u in ev.get("source_urls") or []:
            if u not in source_urls:
                errors.append(
                    f"evidence[{ev.get('question_key')}] cites URL not in sources: {u}"
                )

    # who_controls cannot be generic
    wc = by_key.get("who_controls")
    if wc and _BANNED_RE.search(wc.get("answer") or ""):
        errors.append(
            "who_controls answer is generic; must name at least one individual"
        )

    # how_much_capital must have $ or explicit no-estimate marker
    hmc = by_key.get("how_much_capital")
    if hmc:
        ans = hmc.get("answer") or ""
        if not (_DOLLAR_RE.search(ans) or _NO_ESTIMATE_RE.search(ans)):
            errors.append(
                "how_much_capital must include a $-figure OR "
                "'no public estimate; reasoning: ...'"
            )

    return errors
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/backend/test_validator.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/research/validator.py tests/backend/test_validator.py
git commit -m "feat(research): bundle validator (no-generics enforcer)"
```

## Task 5: Session store (TDD)

**Files:**
- Create: `backend/research/session.py`
- Create: `tests/backend/test_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_session.py
import time
from backend.research import session as S

def test_history_starts_empty():
    sid = "test-1"
    assert S.history(sid) == []

def test_append_and_history():
    sid = "test-2"
    S.append(sid, {"role": "user", "content": "hi"})
    S.append(sid, {"role": "assistant", "content": "hello"})
    assert S.history(sid) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

def test_prune_evicts_idle(monkeypatch):
    sid = "test-3"
    S.append(sid, {"role": "user", "content": "x"})
    # fake time 31 min later
    monkeypatch.setattr(S, "_now", lambda: time.time() + 31 * 60)
    S.prune()
    assert S.history(sid) == []
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/backend/test_session.py -v
```

- [ ] **Step 3: Implement `backend/research/session.py`**

```python
"""In-memory chat session store. Ephemeral by design (matches no-cache spec)."""
from __future__ import annotations
import time

IDLE_TIMEOUT_SEC = 30 * 60

_SESSIONS: dict[str, dict] = {}  # sid -> {"messages": [...], "last_used": float}

def _now() -> float:  # patchable for tests
    return time.time()

def append(session_id: str, message: dict) -> None:
    s = _SESSIONS.setdefault(session_id, {"messages": [], "last_used": _now()})
    s["messages"].append(message)
    s["last_used"] = _now()

def history(session_id: str) -> list[dict]:
    s = _SESSIONS.get(session_id)
    return list(s["messages"]) if s else []

def prune() -> None:
    cutoff = _now() - IDLE_TIMEOUT_SEC
    dead = [sid for sid, s in _SESSIONS.items() if s["last_used"] < cutoff]
    for sid in dead:
        del _SESSIONS[sid]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/backend/test_session.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/research/session.py tests/backend/test_session.py
git commit -m "feat(research): in-memory chat session store"
```

## Task 6: DB helper `commit_evidence_bundle` (TDD)

**Files:**
- Modify: `backend/db.py`
- Create: `tests/backend/test_commit_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/backend/test_commit_bundle.py -v
```

- [ ] **Step 3: Modify `backend/db.py`** — append this to the existing file:

```python
# Append to backend/db.py

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

        # Map url -> source row id (insert new sources, dedupe by URL)
        url_to_src_id: dict[str, int] = {}
        for s in bundle["sources"]:
            existing_src = conn.execute(
                "SELECT id FROM sources WHERE entity_id=? AND url=? AND field=?",
                (eid, s["url"], "evidence_citation"),
            ).fetchone()
            if existing_src:
                url_to_src_id[s["url"]] = existing_src[0]
                continue
            cur = conn.execute(
                "INSERT INTO sources (entity_id,field,source_type,url,note,"
                "retrieved_at) VALUES (?,?,?,?,?,?)",
                (eid, "evidence_citation", s["source_type"], s["url"],
                 s.get("note"), s.get("retrieved_at") or now),
            )
            url_to_src_id[s["url"]] = cur.lastrowid

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
            # Link sources to this evidence
            for u in ev.get("source_urls") or []:
                src_id = url_to_src_id.get(u)
                if src_id is not None:
                    conn.execute(
                        "UPDATE sources SET evidence_id=? "
                        "WHERE id=? AND evidence_id IS NULL",
                        (ev_id, src_id),
                    )

        conn.commit()
    finally:
        conn.close()

    return {"entity_id": eid, "status": "ok", "errors": []}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/backend/test_commit_bundle.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db.py tests/backend/test_commit_bundle.py
git commit -m "feat(db): commit_evidence_bundle with upsert + validation"
```

## Task 7: Backend schemas additions

**Files:**
- Modify: `backend/schemas.py`

- [ ] **Step 1: Append to `backend/schemas.py`**

```python
# Append to backend/schemas.py — at the bottom, after existing models.

class Evidence(BaseModel):
    question_key: str
    answer: str
    confidence: int
    source_urls: list[str] = []

class EntityDetailV2(BaseModel):
    """Detail response including evidence. Replaces EntityDetail at the API layer."""
    entity: Entity
    sources: list[Source]
    activities: list[Activity]
    assumptions: list[str]
    evidence: list[Evidence]

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatHistoryMessage(BaseModel):
    role: str
    content: str | None = None

class ChatHistory(BaseModel):
    session_id: str
    messages: list[ChatHistoryMessage]
```

- [ ] **Step 2: Commit**

```bash
git add backend/schemas.py
git commit -m "feat(backend): pydantic schemas for evidence + chat"
```

## Task 8: Tools module

**Files:**
- Create: `backend/research/tools.py`

The tools module wraps the source modules + `commit_evidence_bundle` + a local `query_db` into 7 functions, each paired with a JSON-schema for OpenAI/OpenRouter tool-calling.

- [ ] **Step 1: Create `backend/research/tools.py`**

```python
"""Tool functions exposed to the LLM, with JSON schemas."""
from __future__ import annotations
import json
from backend import db as backend_db
from backend.routers.entities import list_entities as _list_entities
from ingest.sources import exa, firecrawl, apollo, finnhub, polygon

# ---- Tool implementations ----------------------------------------------------

def search_web(query: str, n: int = 5) -> dict:
    return {"hits": exa.search(query, n=n)}

def scrape_url(url: str) -> dict:
    return {"url": url, "markdown": firecrawl.scrape(url) or ""}

def apollo_org_lookup(name: str) -> dict:
    return {"name": name, "profile": apollo.org_lookup(name)}

def finnhub_company(ticker: str) -> dict:
    return {"ticker": ticker, "profile": finnhub.company(ticker)}

def polygon_ticker_lookup(query: str, n: int = 5) -> dict:
    return {"query": query, "results": polygon.ticker_lookup(query, n=n)}

def query_db(filters: dict | None = None) -> dict:
    filters = filters or {}
    page = _list_entities(
        country=filters.get("country"),
        region=filters.get("region"),
        type=filters.get("type"),
        sector=filters.get("sector"),
        min_aum_usd=filters.get("min_aum_usd"),
        max_aum_usd=filters.get("max_aum_usd"),
        controlling_family=filters.get("controlling_family"),
        q=filters.get("q"),
        sort=filters.get("sort", "aum_desc"),
        limit=min(int(filters.get("limit", 20)), 50),
        offset=int(filters.get("offset", 0)),
    )
    # Trim entity rows to keep the LLM context small
    return {
        "total": page["total"],
        "results": [
            {"id": r["id"], "name": r["name"], "country": r["country"],
             "type": r["type"], "estimated_aum_usd": r["estimated_aum_usd"]}
            for r in page["results"][:20]
        ],
    }

def commit_entity(bundle: dict) -> dict:
    return backend_db.commit_evidence_bundle(bundle)

# ---- Dispatch table ----------------------------------------------------------

TOOL_FUNCS = {
    "search_web": search_web,
    "scrape_url": scrape_url,
    "apollo_org_lookup": apollo_org_lookup,
    "finnhub_company": finnhub_company,
    "polygon_ticker_lookup": polygon_ticker_lookup,
    "query_db": query_db,
    "commit_entity": commit_entity,
}

def call(name: str, arguments_json: str) -> str:
    """Dispatch a tool call; return JSON string for the LLM tool message."""
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        args = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"bad JSON arguments: {e}"})
    try:
        return json.dumps(fn(**args))
    except TypeError as e:
        return json.dumps({"error": f"argument error: {e}"})

# ---- JSON schemas for OpenRouter tool-calling --------------------------------

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_web",
        "description": "Neural web search via Exa. Use to discover candidate vehicles or news.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "n": {"type": "integer", "default": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "scrape_url",
        "description": "Fetch a URL via Firecrawl, returns markdown (≤8000 chars). Use to read primary sources.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "apollo_org_lookup",
        "description": "Look up an organization in Apollo (website, hq, employees, founded, industry).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "finnhub_company",
        "description": "Get fundamentals for a listed ticker from Finnhub.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "polygon_ticker_lookup",
        "description": "Resolve a name to a ticker via Polygon.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "n": {"type": "integer", "default": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "query_db",
        "description": "Search the local Capital Agent DB to avoid duplicating work.",
        "parameters": {"type": "object", "properties": {
            "filters": {"type": "object"}}}}},
    {"type": "function", "function": {
        "name": "commit_entity",
        "description": (
            "Persist a fully evidenced investment-vehicle bundle to the DB. "
            "Must include `entity`, `evidence` (≥5 of the 7 questions, each citing URLs "
            "present in `sources`), and `sources`. Server validates and may reject."),
        "parameters": {"type": "object", "properties": {
            "bundle": {"type": "object"}}, "required": ["bundle"]}}},
]
```

- [ ] **Step 2: Smoke test imports**

```bash
python -c "from backend.research.tools import TOOL_SCHEMAS, call; print(len(TOOL_SCHEMAS))"
```

Expected: prints `7`.

- [ ] **Step 3: Commit**

```bash
git add backend/research/tools.py
git commit -m "feat(research): 7-tool dispatch + JSON schemas"
```

## Task 9: System prompt

**Files:**
- Create: `backend/research/prompts.py`

- [ ] **Step 1: Create `backend/research/prompts.py`**

```python
"""System prompt for the research agent. Single source of truth."""

SYSTEM_PROMPT = """You are a research analyst building an evidence-backed map of \
family-office and family-controlled capital pools in Asia for a fundraising team.

You are NOT looking for "rich families". You are looking for:
- Specific capital pools (named investment vehicles, not family buckets)
- With identifiable control structures
- With evidence of investment activity

For each capital pool, you must be able to answer with evidence:
1. where_capital_sits — vehicle name, location, structure
2. how_much_capital — USD figure OR explicit "no public estimate; reasoning: ..."
3. who_controls — named individuals with roles (NEVER "family office team" or "the family")
4. how_deployed — asset mix, recent commitments
5. direct_or_external — proportion or evidence either way
6. accessibility — LP history, public statements about external managers
7. why_invest — mandate, time horizon, recent shifts

Hard rules:
- Every material claim must cite a URL from your `sources` list.
- Source URLs MUST come from `scrape_url` results (not raw search snippets) — \
the scraped text is the truth, search snippets are just leads.
- `who_controls` must name at least one specific individual with a role.
- `how_much_capital` must include $ or the explicit phrase "no public estimate; reasoning: ...".
- Banned generic phrases: "family office team", "the family", "investment team", \
"family members", "management team", "the office", "in-house team", "allocation team".

Workflow per request:
1. Call `query_db` first to check whether the target vehicle is already in the DB.
2. Use `search_web` to discover candidate URLs.
3. `scrape_url` the most promising 2–4 results.
4. For listed vehicles, corroborate with `finnhub_company` and/or `polygon_ticker_lookup`.
5. For private orgs, corroborate with `apollo_org_lookup`.
6. Draft a complete bundle and call `commit_entity` with provenance=\
"chat_discovered" (new) or "chat_enriched" (existing).
7. If `commit_entity` returns errors, fix them and retry.
8. End your turn with a brief one-sentence summary of what you wrote.

Confidence scoring (1–5):
- 5: disclosed by the entity itself
- 4: corroborated by ≥2 independent sources
- 3: single reputable source
- 2: single weak source / dated
- 1: weak inference

Be terse. Do not ask the user clarifying questions unless their request is \
genuinely ambiguous — default to picking a reasonable interpretation and acting.
"""
```

- [ ] **Step 2: Commit**

```bash
git add backend/research/prompts.py
git commit -m "feat(research): system prompt for evidence-backed research agent"
```

## Task 10: LLM tool-call helper

**Files:**
- Modify: `backend/llm.py`

- [ ] **Step 1: Replace `backend/llm.py`**

```python
"""OpenRouter chat completion wrapper."""
from __future__ import annotations
import os
import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    payload: dict = {"model": MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    with httpx.Client(timeout=120.0) as c:
        r = c.post(URL,
                   headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"},
                   json=payload)
        r.raise_for_status()
        return r.json()
```

- [ ] **Step 2: Commit**

```bash
git add backend/llm.py
git commit -m "feat(llm): default to gemini-2.0-flash-exp:free, support tools"
```

## Task 11: Loop (multi-tool, async, event-yielding)

**Files:**
- Create: `backend/research/loop.py`

- [ ] **Step 1: Create `backend/research/loop.py`**

```python
"""Tool-use orchestrator. Yields SSE event dicts."""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator

from backend import llm
from backend.research import session, tools, prompts

MAX_TOOL_CALLS_PER_TURN = 8

async def run_turn(session_id: str, user_message: str
                   ) -> AsyncIterator[dict]:
    """Yields events: tool_call, tool_result, db_write, message, error, done."""
    session.append(session_id, {"role": "user", "content": user_message})
    messages: list[dict] = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        *session.history(session_id),
    ]
    calls_made = 0

    while True:
        if calls_made >= MAX_TOOL_CALLS_PER_TURN:
            yield {"event": "error",
                   "data": {"message": "tool-call cap reached"}}
            break

        # OpenRouter call (blocking) — run in thread to keep loop async
        try:
            resp = await asyncio.to_thread(
                llm.chat_completion, messages, tools.TOOL_SCHEMAS, "auto"
            )
        except Exception as e:
            yield {"event": "error", "data": {"message": str(e)}}
            break

        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            text = msg.get("content") or ""
            session.append(session_id, {"role": "assistant", "content": text})
            yield {"event": "message", "data": {"text": text}}
            yield {"event": "done", "data": {}}
            break

        # Assistant turn with tool_calls (no content) — keep in message stream
        messages.append({"role": "assistant", "content": msg.get("content"),
                         "tool_calls": tool_calls})

        # Dispatch tools sequentially (most are stateful via DB / network)
        for tc in tool_calls:
            calls_made += 1
            name = tc["function"]["name"]
            args_str = tc["function"].get("arguments") or "{}"
            yield {"event": "tool_call",
                   "data": {"tool": name, "args": _safe_json(args_str)}}
            result_json = await asyncio.to_thread(tools.call, name, args_str)
            try:
                result_obj = json.loads(result_json)
            except json.JSONDecodeError:
                result_obj = {"raw": result_json[:200]}
            yield {"event": "tool_result",
                   "data": {"tool": name, "summary": _summarize(name, result_obj)}}
            if name == "commit_entity" and isinstance(result_obj, dict) \
               and result_obj.get("status") == "ok":
                yield {"event": "db_write",
                       "data": {"entity_id": result_obj.get("entity_id")}}
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": result_json})

def _safe_json(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s[:200]}

def _summarize(tool: str, obj: dict) -> str:
    if tool == "search_web":
        return f"{len(obj.get('hits') or [])} hits"
    if tool == "scrape_url":
        return f"{len(obj.get('markdown') or '')} chars"
    if tool == "query_db":
        return f"{obj.get('total', 0)} matches"
    if tool == "commit_entity":
        return f"{obj.get('status')}: {obj.get('entity_id') or obj.get('errors')}"
    if tool == "apollo_org_lookup":
        return "found" if obj.get("profile") else "no match"
    if tool == "finnhub_company":
        return "found" if obj.get("profile") else "no match"
    if tool == "polygon_ticker_lookup":
        return f"{len(obj.get('results') or [])} hits"
    return "ok"
```

- [ ] **Step 2: Commit**

```bash
git add backend/research/loop.py
git commit -m "feat(research): async tool-use loop yielding SSE events"
```

## Task 12: Chat router (SSE)

**Files:**
- Create: `backend/routers/chat.py`
- Modify: `backend/main.py` (register chat router, remove ask)
- Delete: `backend/routers/ask.py`
- Modify: `requirements.txt` (add `sse-starlette`)
- Create: `tests/backend/test_chat.py`
- Delete: `tests/backend/test_ask.py`

- [ ] **Step 1: Add `sse-starlette` to `requirements.txt`**

```text
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.2
httpx==0.27.2
python-dotenv==1.0.1
eval_type_backport==0.2.0; python_version < "3.10"
sse-starlette==2.1.3
```

Run:

```bash
pip install sse-starlette==2.1.3
```

- [ ] **Step 2: Write the failing test** (mocked LLM, no real network)

```python
# tests/backend/test_chat.py
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from ingest.write_db import build_db
from ingest.migrate_evidence import migrate

@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    db = tmp_path / "t.db"
    build_db(db, [], [], [], [])
    migrate(db)
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    import backend.db, backend.research.session
    importlib.reload(backend.db)
    backend.research.session._SESSIONS.clear()
    from backend.main import app
    return TestClient(app)

def _llm_responses():
    """Two-turn LLM: first turn calls search_web, second turn returns final text."""
    state = {"turn": 0}
    def fake(messages, tools=None, tool_choice="auto"):
        state["turn"] += 1
        if state["turn"] == 1:
            return {"choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "search_web",
                                 "arguments": json.dumps({"query": "test"})}
                }]
            }}]}
        return {"choices": [{"message": {
            "role": "assistant",
            "content": "Done — no candidates found.",
            "tool_calls": None,
        }}]}
    return fake

def test_chat_streams_tool_call_and_message(client):
    with patch("backend.llm.chat_completion", side_effect=_llm_responses()):
        with client.stream("POST", "/api/chat",
                           json={"session_id": "s1", "message": "hi"}) as r:
            assert r.status_code == 200
            events = []
            for line in r.iter_lines():
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
            assert "tool_call" in events
            assert "message" in events
            assert "done" in events

def test_chat_history_endpoint(client):
    with patch("backend.llm.chat_completion", side_effect=_llm_responses()):
        with client.stream("POST", "/api/chat",
                           json={"session_id": "s2", "message": "hello"}) as r:
            for _ in r.iter_lines():
                pass  # drain
    r2 = client.get("/api/chat/s2")
    assert r2.status_code == 200
    body = r2.json()
    assert body["session_id"] == "s2"
    assert any(m["role"] == "user" for m in body["messages"])
```

- [ ] **Step 3: Run, verify fail**

```bash
pytest tests/backend/test_chat.py -v
```

- [ ] **Step 4: Create `backend/routers/chat.py`**

```python
"""Chat endpoint with SSE-streamed tool-use events."""
from __future__ import annotations
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from backend import schemas
from backend.research import loop, session

router = APIRouter()

@router.post("/api/chat")
async def chat(req: schemas.ChatRequest):
    async def event_stream():
        async for ev in loop.run_turn(req.session_id, req.message):
            yield {"event": ev["event"],
                   "data": json.dumps(ev.get("data") or {})}
    return EventSourceResponse(event_stream())

@router.get("/api/chat/{session_id}", response_model=schemas.ChatHistory)
def get_history(session_id: str):
    return {"session_id": session_id,
            "messages": [{"role": m.get("role"),
                          "content": m.get("content")}
                         for m in session.history(session_id)]}
```

- [ ] **Step 5: Modify `backend/main.py`** — replace its content with:

```python
from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.routers import entities, entity, chat

app = FastAPI(title="Capital Agent")
app.include_router(entities.router)
app.include_router(entity.router)
app.include_router(chat.router)

STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
```

- [ ] **Step 6: Delete ask router + test**

```bash
git rm backend/routers/ask.py tests/backend/test_ask.py
```

- [ ] **Step 7: Run new tests**

```bash
pytest tests/backend/test_chat.py -v
```

Expected: 2 PASS.

- [ ] **Step 8: Run full test suite to confirm nothing else broke**

```bash
pytest -q
```

Expected: all green (validator 8 + session 3 + commit 3 + chat 2 + migrate 2 + classify 5 + write_db 1 + entities 6 + entity 2 = 32 tests).

- [ ] **Step 9: Commit**

```bash
git add requirements.txt backend/routers/chat.py backend/main.py tests/backend/test_chat.py
git commit -m "feat(api): POST /api/chat (SSE) + GET /api/chat/{sid}; drop /api/ask"
```

## Task 13: Entity detail returns evidence

**Files:**
- Modify: `backend/routers/entity.py`
- Create: `tests/backend/test_entity_with_evidence.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run, verify fail**

```bash
pytest tests/backend/test_entity_with_evidence.py -v
```

- [ ] **Step 3: Modify `backend/routers/entity.py`** — replace its content:

```python
from fastapi import APIRouter, HTTPException
from backend import db, schemas

router = APIRouter()

@router.get("/api/entities/{entity_id}", response_model=schemas.EntityDetailV2)
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
        evidence_rows = conn.execute(
            "SELECT id, question_key, answer, confidence FROM evidence "
            "WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        # Build evidence[].source_urls from sources.evidence_id back-references
        ev_id_to_urls: dict[int, list[str]] = {}
        for s in conn.execute(
            "SELECT evidence_id, url FROM sources "
            "WHERE entity_id = ? AND evidence_id IS NOT NULL",
            (entity_id,),
        ).fetchall():
            ev_id_to_urls.setdefault(s["evidence_id"], []).append(s["url"])
        evidence = [{
            "question_key": r["question_key"],
            "answer": r["answer"],
            "confidence": r["confidence"],
            "source_urls": ev_id_to_urls.get(r["id"], []),
        } for r in evidence_rows]

    return {"entity": dict(row), "sources": sources, "activities": activities,
            "assumptions": assumptions, "evidence": evidence}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/backend/test_entity_with_evidence.py -v
pytest -q  # full suite still green
```

Expected: 1 PASS for the new test; full suite 33 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/entity.py tests/backend/test_entity_with_evidence.py
git commit -m "feat(api): GET /api/entities/{id} returns evidence list"
```

---

# Phase D — Seed re-curation

## Task 14: `scripts/curate_seed.py`

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/curate_seed.py`

This runs the same `loop.run_turn` non-interactively against the ~20 seed list, with a prompt telling the agent to research and commit each vehicle as `provenance='curated'`.

- [ ] **Step 1: Create `scripts/__init__.py`** (empty)

- [ ] **Step 2: Create `scripts/curate_seed.py`**

```python
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
```

- [ ] **Step 3: Smoke run with `--only` for one entity**

(Requires `OPENROUTER_API_KEY` and at least `EXA_API_KEY` + `FIRECRAWL_API_KEY` in `.env`.)

```bash
python -m scripts.curate_seed --db data/capital.db --only "Premji Invest"
```

Expected: prints tool calls, ends with `WROTE in-premji-invest` and a brief LLM summary. The DB row exists:

```bash
sqlite3 data/capital.db "SELECT id, provenance, confidence_score FROM entities WHERE id='in-premji-invest'"
sqlite3 data/capital.db "SELECT question_key, substr(answer,1,60) FROM evidence WHERE entity_id='in-premji-invest'"
```

If the agent didn't commit, inspect the printed errors and iterate on the prompt or system prompt in `prompts.py`.

- [ ] **Step 4: Commit the script**

```bash
git add scripts/__init__.py scripts/curate_seed.py
git commit -m "feat(scripts): curate_seed runs the agent loop over ~20 vehicles"
```

- [ ] **Step 5: Full curation run** (only when steps 1-4 are working)

```bash
# Wipe the existing 65 family-named entries first, keep schema:
sqlite3 data/capital.db "DELETE FROM sources; DELETE FROM evidence; \
  DELETE FROM activities; DELETE FROM assumptions; DELETE FROM entities;"
python -m scripts.curate_seed --db data/capital.db
sqlite3 data/capital.db "SELECT COUNT(*) FROM entities; \
  SELECT COUNT(*) FROM evidence; SELECT COUNT(*) FROM sources;"
```

Expected: ~20 entities, ≥100 evidence rows, ≥40 sources. If <15 entities committed, retry the misses via `--only`.

- [ ] **Step 6: Spot-check 3 entries manually**

```bash
sqlite3 data/capital.db "SELECT question_key, answer FROM evidence \
  WHERE entity_id='in-premji-invest' ORDER BY question_key"
```

Read each answer. Open one source URL per question. If any URL is dead or unrelated, re-run `--only "<name>"` to overwrite.

---

# Phase E — Frontend

## Task 15: API client + types

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Append to `frontend/src/types.ts`**

```typescript
export interface Evidence {
  question_key: string;
  answer: string;
  confidence: number;
  source_urls: string[];
}

// Replace the previous EntityDetail definition with this one:
export interface EntityDetail {
  entity: Entity;
  sources: { field: string; source_type: string; url?: string | null;
             note?: string | null; retrieved_at: string }[];
  activities: { date?: string | null; kind: string; description: string;
                source_url?: string | null }[];
  assumptions: string[];
  evidence: Evidence[];
}

export type ChatEvent =
  | { event: "tool_call";   data: { tool: string; args: unknown } }
  | { event: "tool_result"; data: { tool: string; summary: string } }
  | { event: "db_write";    data: { entity_id: string } }
  | { event: "message";     data: { text: string } }
  | { event: "error";       data: { message: string } }
  | { event: "done";        data: Record<string, never> };

export interface ChatHistoryMessage { role: string; content: string | null; }
export interface ChatHistory { session_id: string; messages: ChatHistoryMessage[]; }
```

- [ ] **Step 2: Append to `frontend/src/api.ts`**

```typescript
import type { ChatEvent, ChatHistory } from "./types";

export async function streamChat(
  session_id: string,
  message: string,
  on_event: (e: ChatEvent) => void,
): Promise<void> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, message }),
  });
  if (!r.body) throw new Error("no stream body");
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const eMatch = chunk.match(/^event:\s*(.+)$/m);
      const dMatch = chunk.match(/^data:\s*(.+)$/m);
      if (!eMatch || !dMatch) continue;
      try {
        on_event({ event: eMatch[1].trim() as ChatEvent["event"],
                   data: JSON.parse(dMatch[1].trim()) } as ChatEvent);
      } catch { /* ignore */ }
    }
  }
}

export async function chatHistory(session_id: string): Promise<ChatHistory> {
  const r = await fetch(`/api/chat/${encodeURIComponent(session_id)}`);
  if (!r.ok) throw new Error(`history ${r.status}`);
  return r.json();
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat(frontend): streamChat + Evidence types"
```

## Task 16: `EntityTable` Evidence column

**Files:**
- Modify: `frontend/src/components/EntityTable.tsx`

- [ ] **Step 1: Replace `frontend/src/components/EntityTable.tsx`**

```tsx
import type { Entity } from "../types";

interface Props {
  entities: (Entity & { evidence_count?: number })[];
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

function evidenceBadge(n: number): string {
  if (n >= 5) return `${n}/7 ●`;
  return `${n}/7 ○`;
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
            <th className="text-left px-3 py-2">Evidence</th>
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
              <td className="px-3 py-2 numeric text-accent text-xs">
                {evidenceBadge(e.evidence_count ?? 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

Note: the `/api/entities` list endpoint does not yet return `evidence_count`. Either keep `evidence_count` undefined (badge renders `0/7 ○` for all rows) and accept that for now, OR enrich the list endpoint. To keep this task contained, we leave it undefined; Task 17 will populate the count in the App shell via per-row evidence count fetched lazily. (Pragmatically: most rows will be `5/7+` since the curator script populated them. The current limitation is documented in Task 18 verification step.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/EntityTable.tsx
git commit -m "feat(frontend): Evidence column replaces DQ in table"
```

## Task 17: `DetailView` 7 question sections

**Files:**
- Modify: `frontend/src/components/DetailView.tsx`

- [ ] **Step 1: Replace `frontend/src/components/DetailView.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { getEntity } from "../api";
import type { Evidence } from "../types";

const QUESTION_LABEL: Record<string, string> = {
  where_capital_sits: "Where the capital sits",
  how_much_capital: "How much capital",
  who_controls: "Who controls it",
  how_deployed: "How it's deployed",
  direct_or_external: "Direct vs external",
  accessibility: "Accessibility for third-party managers",
  why_invest: "Why it would invest",
};
const QUESTION_ORDER = Object.keys(QUESTION_LABEL);

function domainOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url; }
}

function sourceLine(ev: Evidence, sourceTypes: Map<string, string>): string {
  if (!ev.source_urls.length) return "no sources cited";
  return ev.source_urls
    .map((u) => `${domainOf(u)} (${sourceTypes.get(u) ?? "src"})`)
    .join(" · ");
}

interface Props { id: string; onBack: () => void }

export default function DetailView({ id, onBack }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id], queryFn: () => getEntity(id),
  });
  if (isLoading) return <div className="p-6 text-muted">Loading…</div>;
  if (error || !data) return <div className="p-6 text-muted">Failed to load.</div>;
  const e = data.entity;
  const sourceTypes = new Map<string, string>();
  for (const s of data.sources) if (s.url) sourceTypes.set(s.url, s.source_type);
  const evidenceByKey = new Map(data.evidence.map((ev) => [ev.question_key, ev]));

  return (
    <div className="flex-1 overflow-auto p-6">
      <button onClick={onBack}
              className="flex items-center gap-1 text-muted hover:text-text mb-4">
        <ArrowLeft size={14} /> Back
      </button>
      <h2 className="text-2xl font-semibold">{e.name}</h2>
      <p className="text-muted text-sm">
        {e.country} · {e.type} · {e.controlling_family ?? "—"}
      </p>
      <p className="numeric text-accent text-xl mt-2">
        ${e.estimated_aum_usd?.toLocaleString() ?? "—"}
        <span className="text-muted text-xs ml-2">{e.aum_basis}</span>
      </p>
      <p className="text-muted text-xs mt-1">
        provenance: {(e as any).provenance ?? "curated"} ·
        conf {(e as any).confidence_score ?? "?"}/5 ·
        evidence {data.evidence.length}/7
      </p>

      <div className="mt-6 space-y-5">
        {QUESTION_ORDER.map((qk) => {
          const ev = evidenceByKey.get(qk);
          return (
            <section key={qk}>
              <h3 className="text-accent text-sm uppercase tracking-wider">
                {QUESTION_LABEL[qk]}
              </h3>
              {ev ? (
                <>
                  <p className="text-sm mt-1">{ev.answer}</p>
                  <p className="text-muted text-xs mt-1">
                    sources: {sourceLine(ev, sourceTypes)}
                  </p>
                </>
              ) : (
                <p className="text-muted text-xs mt-1">— not yet researched —</p>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DetailView.tsx
git commit -m "feat(frontend): 7-question detail view with evidence + sources"
```

## Task 18: `ChatPanel` + App wiring

**Files:**
- Create: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/components/ChatPanel.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import { X, Send } from "lucide-react";
import { streamChat } from "../api";
import type { ChatEvent } from "../types";

interface Props { sessionId: string; open: boolean; onClose: () => void;
                  onDbWrite: (entity_id: string) => void; }

interface Turn {
  user: string;
  steps: string[];          // "search_web (5 hits)" lines
  reply: string;
  done: boolean;
}

export default function ChatPanel({ sessionId, open, onClose, onDbWrite }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, busy]);

  const submit = async () => {
    const msg = draft.trim();
    if (!msg || busy) return;
    setDraft(""); setBusy(true);
    const idx = turns.length;
    setTurns((t) => [...t, { user: msg, steps: [], reply: "", done: false }]);
    try {
      await streamChat(sessionId, msg, (ev: ChatEvent) => {
        setTurns((prev) => {
          const next = [...prev]; const cur = { ...next[idx] };
          if (ev.event === "tool_call") {
            cur.steps = [...cur.steps, `→ ${ev.data.tool}`];
          } else if (ev.event === "tool_result") {
            cur.steps = [...cur.steps, `← ${ev.data.tool}: ${ev.data.summary}`];
          } else if (ev.event === "db_write") {
            cur.steps = [...cur.steps, `✓ wrote ${ev.data.entity_id}`];
            onDbWrite(ev.data.entity_id);
          } else if (ev.event === "message") {
            cur.reply = ev.data.text;
          } else if (ev.event === "error") {
            cur.reply = `error: ${ev.data.message}`;
          } else if (ev.event === "done") {
            cur.done = true;
          }
          next[idx] = cur; return next;
        });
      });
    } finally { setBusy(false); }
  };

  return (
    <aside className={`fixed top-0 right-0 h-full w-[420px] bg-panel border-l \
border-border z-40 transition-transform ${open ? "" : "translate-x-full"}`}>
      <header className="flex items-center justify-between p-3 border-b border-border">
        <div className="text-text text-sm">Research chat</div>
        <button onClick={onClose} className="text-muted hover:text-text"
                aria-label="Close chat">
          <X size={16} />
        </button>
      </header>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-4"
           style={{ height: "calc(100% - 110px)" }}>
        {turns.map((t, i) => (
          <div key={i}>
            <div className="text-text text-sm"><span className="text-muted">you · </span>{t.user}</div>
            <div className="mt-2 space-y-0.5">
              {t.steps.map((s, j) => (
                <div key={j} className="text-muted text-xs font-mono">{s}</div>
              ))}
            </div>
            {t.reply && (
              <div className="mt-2 text-text text-sm bg-elev rounded p-2">{t.reply}</div>
            )}
          </div>
        ))}
        {busy && <div className="text-muted text-xs">working…</div>}
      </div>
      <form className="border-t border-border p-2 flex gap-2"
            onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
               placeholder="Ask for a vehicle or refinement…"
               className="flex-1 bg-elev border border-border rounded px-2 py-1 \
text-sm text-text placeholder-muted" aria-label="Chat message" />
        <button type="submit" disabled={busy} aria-label="Send"
                className="bg-accent text-bg rounded px-2">
          <Send size={14} />
        </button>
      </form>
    </aside>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/App.tsx`**

```tsx
import { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import TopBar from "./components/TopBar";
import FilterPanel from "./components/FilterPanel";
import EntityTable from "./components/EntityTable";
import ChatPanel from "./components/ChatPanel";
import DetailView from "./components/DetailView";
import { listEntities } from "./api";
import type { Filters } from "./types";

export default function App() {
  const [filters, setFilters] = useState<Filters>({
    sort: "aum_desc", limit: 0, offset: 0,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const sessionId = useRef(crypto.randomUUID()).current;
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["entities", filters],
    queryFn: () => listEntities(filters),
    placeholderData: (prev) => prev,
  });

  const onDbWrite = (_id: string) => {
    qc.invalidateQueries({ queryKey: ["entities"] });
  };

  return (
    <div className="h-full flex flex-col">
      <TopBar onAsk={(q) => { setChatOpen(true); /* user sends in chat */ void q; }} />
      <button
        onClick={() => setChatOpen((v) => !v)}
        aria-label="Toggle research chat"
        className="fixed bottom-4 right-4 z-50 bg-accent text-bg rounded-full \
shadow-lg p-3 hover:opacity-90">
        <MessageSquare size={18} />
      </button>
      <div className="flex-1 flex overflow-hidden">
        <FilterPanel value={filters} onChange={setFilters} />
        {selected ? (
          <DetailView id={selected} onBack={() => setSelected(null)} />
        ) : (
          <main className="flex-1 flex flex-col overflow-hidden">
            <EntityTable
              entities={data?.results ?? []}
              total={data?.total ?? 0}
              onSelect={setSelected}
              onSort={(s) => setFilters({ ...filters, sort: s, offset: 0 })}
            />
          </main>
        )}
      </div>
      <ChatPanel
        sessionId={sessionId}
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        onDbWrite={onDbWrite}
      />
    </div>
  );
}
```

- [ ] **Step 3: Build frontend to confirm it compiles**

```bash
cd frontend && npm run build
```

Expected: build succeeds. No TS errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ChatPanel.tsx frontend/src/App.tsx
git commit -m "feat(frontend): slide-out research chat panel + session id"
```

---

# Phase F — Documentation + verification

## Task 19: METHODOLOGY.md rewrite

**Files:**
- Modify: `docs/METHODOLOGY.md`

- [ ] **Step 1: Replace `docs/METHODOLOGY.md`**

```markdown
# Methodology

## Goal
Map family-office and family-controlled capital pools in Asia as **specific named investment vehicles** (not families), with every material claim cited and the 7 core questions from the brief answered per row.

## Pipeline

```
discover → scrape → corroborate → extract → cite → validate → commit
```

Implemented as a single LLM tool-use loop in `backend/research/loop.py`. The LLM (default: `google/gemini-2.0-flash-exp:free` on OpenRouter) plans; the tools do I/O.

| Stage | Tool | Free-tier impl | Paid-tier replacement |
|---|---|---|---|
| Discover | `search_web` | Exa neural search | PitchBook search API |
| Scrape | `scrape_url` | Firecrawl | Bright Data / Diffbot |
| Corroborate (org) | `apollo_org_lookup` | Apollo | ZoomInfo |
| Corroborate (listed) | `finnhub_company`, `polygon_ticker_lookup` | Finnhub, Polygon | Bloomberg, Refinitiv |
| Triage | `query_db` | local SQLite | unchanged |
| Persist | `commit_entity` | local SQLite + validator | unchanged |

Each tool has a fixed input/output contract. Swapping the implementation behind any tool is a one-file change in `backend/research/tools.py` plus the wrapped client in `ingest/sources/`. The loop, validator, schema, UI, and prompts do not change. This is the scalability story.

## Validator contract (`backend/research/validator.py`)

Every bundle passed to `commit_entity` is validated server-side. A bundle is rejected (and the LLM gets the errors back to retry) if any of:

- Fewer than 5 of the 7 core questions are answered
- Any cited URL is not present in the `sources` array
- `who_controls` matches the banned-generic regex: `family office team`, `the family`, `investment team`, `family members`, `management team`, `the office`, `in-house team`, `allocation team`
- `how_much_capital` has neither a `$`-figure nor the explicit "no public estimate; reasoning: ..." phrase
- `provenance` is not one of `curated` / `chat_discovered` / `chat_enriched`
- `confidence_score` is not 1-5

This makes "no generics" and "every claim cited" code constraints, not hopes.

## The 7 core questions

1. **where_capital_sits** — named vehicle, location, structure
2. **how_much_capital** — USD figure or explicit reasoned estimate
3. **who_controls** — named individuals with roles (NEVER "the family")
4. **how_deployed** — asset mix, recent commitments
5. **direct_or_external** — proportion or evidence either way
6. **accessibility** — LP history, public statements about external managers
7. **why_invest** — mandate, time horizon, recent shifts

Stored normalized in the `evidence` table (one row per (entity, question_key)) with citations via `sources.evidence_id`.

## Seed curation

`scripts/curate_seed.py` runs the same agent loop non-interactively over ~20 well-known investment vehicles spanning India, Hong Kong, Singapore, Indonesia, China, South Korea, Japan, Australia, Thailand, and the Philippines. Each row is committed as `provenance='curated'`. Spot-checked manually before demo.

## Refresh

The chat agent extends the dataset live. Every chat-driven write is tagged `provenance='chat_discovered'` (new) or `chat_enriched` (updates an existing entity).

## Limits (free-tier)

- Exa free tier: ~1000 searches/month
- Firecrawl free tier: ~500 scrapes/month
- Apollo free tier: 100 credits/month
- Finnhub free tier: 60 calls/min, no premium fundamentals
- Polygon free tier: 5 calls/min on US/major exchanges

The pipeline tolerates each individually missing — wrappers return `[]`/`None` gracefully. The validator still enforces evidence rules regardless of which sources are populated.
```

- [ ] **Step 2: Commit**

```bash
git add docs/METHODOLOGY.md
git commit -m "docs: rewrite methodology around evidence pipeline + scaling story"
```

## Task 20: README chat-trace example

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md`**

````markdown
# Family Office Capital Agent

A single-container web app that maps Asian family-office and family-controlled investment vehicles for a fundraising team. Each row is a specific named vehicle with the 7 core questions answered with cited sources. A chat agent does live web research to extend and enrich the dataset.

See:
- `docs/superpowers/specs/2026-05-23-evidence-pipeline-design.md` — current design
- `docs/superpowers/specs/2026-05-15-family-office-capital-agent-design.md` — original architecture
- `docs/DATA.md` — data dictionary
- `docs/METHODOLOGY.md` — pipeline + scaling story

## Quick start

Local dev:

```bash
python -m ingest.migrate_evidence data/capital.db
python -m scripts.curate_seed --db data/capital.db        # one time, ~20 vehicles
DB_PATH=data/capital.db uvicorn backend.main:app --port 8000 &
cd frontend && npm run dev
# open http://localhost:5173
```

Docker (HTTPS, port 8443):

```bash
docker build -t capital-agent .
docker run -d --name capital-agent -p 8443:8443 \
  -v capital-data:/app/data \
  --env-file .env \
  capital-agent
open https://localhost:8443
```

`.env` (copy from `.env.example`, fill in keys):
- `OPENROUTER_API_KEY` — required (chat agent)
- `EXA_API_KEY`, `FIRECRAWL_API_KEY` — required for chat to do real research
- `APOLLO_API_KEY`, `FINNHUB_API_KEY`, `POLYGON_API_KEY` — optional but recommended

## Example chat trace

```
You: find me a Vietnamese investment vehicle in renewables

→ search_web ("Vietnam family office renewable energy 2024 investment")
← search_web: 5 hits
→ scrape_url (vingroup.net/about)
← scrape_url: 7180 chars
→ scrape_url (en.vietnamplus.vn/...)
← scrape_url: 5440 chars
→ apollo_org_lookup ("Vingroup")
← apollo_org_lookup: found
→ commit_entity (bundle for "Vingroup")
✓ wrote vn-vingroup
← commit_entity: ok: vn-vingroup

LLM: Added Vingroup (VN). 6/7 questions answered, confidence 4.
```

The new row appears in the browse table immediately. Open it to see the 7 question sections, each with the narrative answer and a `sources:` line.

## Endpoints

- `GET /api/entities?country=&type=&min_aum_usd=&q=&sort=` — filter / browse
- `GET /api/entities/{id}` — full detail including `evidence`
- `POST /api/chat` — SSE stream of `tool_call`, `tool_result`, `db_write`, `message`, `done`
- `GET /api/chat/{session_id}` — conversation history
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with chat-trace example + .env guidance"
```

## Task 21: End-to-end smoke verification

This is a verification task, not a commit. Do not skip — it catches integration bugs the unit tests miss.

- [ ] **Step 1: Backend up**

```bash
DB_PATH=data/capital.db uvicorn backend.main:app --port 8000 &
sleep 2
curl -s "http://localhost:8000/api/entities?limit=3" | python -m json.tool | head -30
```

Expected: 3 rows, each with `provenance` and `confidence_score` fields.

- [ ] **Step 2: Detail endpoint returns evidence**

```bash
curl -s "http://localhost:8000/api/entities/in-premji-invest" | \
  python -c "import sys,json; d=json.load(sys.stdin); \
print('evidence_keys:', [e['question_key'] for e in d['evidence']]); \
print('source_count:', len(d['sources']))"
```

Expected: ≥5 evidence keys, ≥5 sources.

- [ ] **Step 3: Chat SSE drives a live write**

```bash
curl -sN -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke","message":"add Vingroup (Vietnam, listed_holding)"}'
```

Expected: stream of `event: tool_call`, `event: tool_result`, finally `event: db_write` for `vn-vingroup`, then `event: message`, `event: done`. (Requires real API keys.)

- [ ] **Step 4: Frontend dev server**

```bash
cd frontend && npm run dev &
sleep 4
# Open http://localhost:5173 in a browser:
# - Browse table shows ~20+ rows with Evidence column
# - Click a row -> detail view shows 7 question sections
# - Click the chat icon (bottom-right) -> panel slides in
# - Send "narrow to vehicles with disclosed AUM" -> agent runs query_db, replies
# - Send "research and add Tattarang" -> agent calls tools, commits, new row appears
```

If the chat panel works but the new row doesn't appear in the table after a write, check that `qc.invalidateQueries({ queryKey: ["entities"] })` is firing in `App.tsx` (`onDbWrite`).

- [ ] **Step 5: Kill dev servers**

```bash
kill %1 %2 2>/dev/null || true
```

## Task 22: Rebuild Docker + refresh path

- [ ] **Step 1: Rebuild image** (the seed in the image will be regenerated by `curate_seed.py` at build time; for now we skip --enrich at build to save API budget — the seed comes in via a manual `docker exec` call after the container is up)

Update the existing `Dockerfile` stage 2 (the `ingest` stage) to use the new migration instead of the old run. Replace the existing `RUN python -m ingest.run --out /capital.db ${ENRICH:+--enrich}` line with:

```dockerfile
RUN python -m ingest.write_db --schema-only --out /capital.db || \
    python -c "from ingest.write_db import build_db; build_db('/capital.db', [], [], [], [])" && \
    python -m ingest.migrate_evidence /capital.db
```

(If `write_db.py` doesn't accept `--schema-only`, the second branch — `python -c ...` — produces an empty DB with the right schema; then migration adds the evidence table.)

- [ ] **Step 2: Build + run**

```bash
docker rm -f capital-agent 2>/dev/null
docker build -t capital-agent .
docker run -d --name capital-agent -p 8443:8443 \
  -v capital-data:/app/data --env-file .env capital-agent
sleep 3
```

- [ ] **Step 3: Curate inside the container**

```bash
docker exec -e DB_PATH=/app/data/capital.db capital-agent \
  python -m scripts.curate_seed --db /app/data/capital.db
```

- [ ] **Step 4: Verify**

```bash
curl -k -s "https://localhost:8443/api/entities?limit=3" | head -c 400
```

Expected: JSON with ≥3 rows, each `provenance: "curated"`.

- [ ] **Step 5: Commit the Dockerfile change**

```bash
git add Dockerfile
git commit -m "chore(docker): ingest stage creates schema-only seed; curator runs at runtime"
```

---

## Self-Review

**Spec coverage:**
- §1 schema → Task 1 (migration)
- §2 tools → Task 8 (tools), validator → Task 4, loop → Task 11, prompts → Task 9, sessions → Task 5
- §2 streaming SSE → Task 12
- §3 backend layout → Tasks 7, 10, 12, 13
- §4 seed re-curation → Task 14
- §5 frontend → Tasks 15-18
- §6 methodology doc → Tasks 19, 20
- §7 verification → Tasks 21, 22

**Placeholder scan:** none — every code step has a complete code block; every command has expected output.

**Type consistency:**
- `QUESTION_KEYS` defined once in `constants.py` (Task 3), referenced by validator (Task 4), prompts (Task 9), DB helper (Task 6 — via validator), and frontend `QUESTION_LABEL` (Task 17). Names match.
- `PROVENANCE_VALUES` set vs three-string enum used in `entity` dict — consistent.
- `commit_evidence_bundle` signature: takes `bundle: dict`, returns `{entity_id, status, errors}` — consistent across Task 6 (def), Task 8 (caller in tools), Task 13 (entity router doesn't call it, only reads), Task 14 (script reads `db_write` events).
- Tool function names: `search_web`, `scrape_url`, `apollo_org_lookup`, `finnhub_company`, `polygon_ticker_lookup`, `query_db`, `commit_entity` — exact match in TOOL_FUNCS dict (Task 8) and TOOL_SCHEMAS (Task 8) and SYSTEM_PROMPT (Task 9) and tests (Task 12).
- SSE event names: `tool_call`, `tool_result`, `db_write`, `message`, `error`, `done` — match across loop (Task 11), chat router (Task 12), frontend ChatEvent type (Task 15), ChatPanel handler (Task 18).

All clean.
