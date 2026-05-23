# Capital Agent — Evidence-Backed Redesign

**Date:** 2026-05-23
**Status:** Approved (brainstorm → spec)
**Supersedes:** parts of `docs/superpowers/specs/2026-05-15-family-office-capital-agent-design.md` (data model, ingestion strategy, ask endpoint). Existing browse table and dark-theme UI stay.

## Context

The current app surfaces ~63 Asian "families" with shallow fields and a one-shot `/api/ask` LLM endpoint that only queries the existing DB. The `sources`, `activities`, `assumptions` tables exist but are empty. The assessor (the user is a candidate for an asset-management data-scientist role) needs evidence-backed **investment vehicles**, not family names, with all 7 core questions from the brief answered per row.

Free APIs only for the demo: Exa, Firecrawl, Apollo (already wired as stubs); Finnhub, Polygon, AlphaVantage (re-add). The methodology must demonstrably scale to paid sources (PitchBook, Preqin, Bloomberg).

## Goal

For each capital pool surfaced, answer with evidence:

1. **Where the capital sits** (vehicle name, location, structure)
2. **How much capital** (USD figure or explicit reasoned estimate)
3. **Who controls it** (named individuals with roles — not "the family")
4. **How it's currently deployed** (asset mix, recent commitments)
5. **Direct vs external** (proportion or evidence either way)
6. **Accessibility for third-party managers** (LP history, public statements)
7. **Why it would invest** (mandate, time horizon, recent shifts)

Every material claim cites a URL. No generic answers. Methodology must demonstrably scale to paid data sources.

## 1. Data model (additive — no destructive migration)

`entities` gains two columns:

```sql
ALTER TABLE entities ADD COLUMN provenance TEXT NOT NULL DEFAULT 'curated';
   -- 'curated' | 'chat_discovered' | 'chat_enriched'
ALTER TABLE entities ADD COLUMN confidence_score INTEGER NOT NULL DEFAULT 3;
```

New normalized `evidence` table, one row per (entity, question):

```sql
CREATE TABLE evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL REFERENCES entities(id),
  question_key TEXT NOT NULL,    -- enum: where_capital_sits |
                                  -- how_much_capital | who_controls |
                                  -- how_deployed | direct_or_external |
                                  -- accessibility | why_invest
  answer TEXT NOT NULL,           -- 1-3 sentence narrative
  confidence INTEGER NOT NULL,    -- 1-5
  created_at TEXT NOT NULL,
  UNIQUE(entity_id, question_key)
);
CREATE INDEX idx_evidence_entity ON evidence(entity_id);
```

`sources` gains a nullable FK so each citation ties to a specific Q&A:

```sql
ALTER TABLE sources ADD COLUMN evidence_id INTEGER REFERENCES evidence(id);
```

Existing rows in `sources` keep `evidence_id = NULL` (entity-level provenance, e.g., the original curated `source_url`). Nothing in `entities`, `activities`, `assumptions` is removed.

Migration: a small `ingest/migrate_evidence.py` runs `ALTER TABLE` and `CREATE TABLE` statements once against the existing `data/capital.db`. Idempotent (`PRAGMA table_info` / `sqlite_master` check before each statement).

## 2. Research pipeline (`backend/research/`)

A new module that orchestrates a multi-turn LLM tool-use loop. The LLM plans; the tools do I/O.

### Tools (7 max, kept narrow)

| Tool | Implementation | Returns | Purpose |
|---|---|---|---|
| `search_web(query, n=5)` | Exa | `[{url, title, snippet}]` | Discovery |
| `scrape_url(url)` | Firecrawl | markdown (≤8k chars) | Pull source-of-truth text |
| `apollo_org_lookup(name)` | Apollo | `{website, hq_country, employees, founded, industry}` | Verify org basics |
| `finnhub_company(ticker)` | Finnhub | `{market_cap, name, exchange, industry}` | Listed-vehicle facts (re-add) |
| `polygon_ticker_lookup(query)` | Polygon | `[{ticker, name, country}]` | Resolve name → ticker (re-add) |
| `query_db(filters)` | local SQLite | matching entities | Check duplicates |
| `commit_entity(bundle)` | local SQLite | `{entity_id, status, errors}` | Auto-write the vetted bundle |

The three existing source wrappers (`exa.py`, `firecrawl.py`, `apollo.py`) keep their graceful-fail interface; `finnhub.py` and `polygon.py` are re-added (the user has those keys too).

### The bundle `commit_entity` accepts

```python
{
  "entity": {
    "name": str, "type": str, "country": str, "region": str,
    "controlling_family": str | None,
    "ticker": str | None, "exchange": str | None,
    "estimated_aum_usd": float | None, "aum_basis": str,
    "sectors": [str], "deployment": str, "accessibility": str,
    "provenance": "chat_discovered" | "chat_enriched",
    "confidence_score": int  # 1-5
  },
  "evidence": [
    {"question_key": str, "answer": str,
     "confidence": int, "source_urls": [str]},
    ...  # ≥5 of 7 questions
  ],
  "sources": [
    {"url": str, "source_type": str, "note": str, "retrieved_at": str},
    ...  # union of all source_urls referenced in evidence
  ]
}
```

### Validator (`backend/research/validator.py`)

Server-side guard before any DB write. Rejects with structured error if:

- `evidence` has fewer than 5 question keys
- Any `evidence[i].source_urls` references a URL not in `sources`
- `who_controls` answer matches `BANNED_GENERIC` regex (`family office team|the family|investment team|family members|management team`)
- `how_much_capital` answer has no `$` and no explicit "no public estimate; reasoning:" phrase
- `confidence_score` not 1-5
- `provenance` not in {`chat_discovered`, `chat_enriched`}

When rejected, the agent gets the error list back in the tool response and retries. This makes "no generics" a code constraint, not a hope.

### Loop (`backend/research/loop.py`)

Per user message:

1. Append user message to session history (`session.py`, in-memory dict keyed by `session_id`, 30-min idle pruning).
2. Call OpenRouter chat completion with system prompt + history + tool schemas, `tool_choice="auto"`.
3. If LLM emits tool calls: execute them (independent calls run via `asyncio.gather`); append each result; loop.
4. Hard cap: 8 tool calls per turn (cost/runtime ceiling).
5. When LLM emits final assistant text: end turn.

### Streaming

`POST /api/chat` returns Server-Sent Events:

```
event: tool_call    data: {"tool":"search_web","args":{"query":"Indonesian SFOs renewables"}}
event: tool_result  data: {"tool":"search_web","summary":"5 hits"}
event: tool_call    data: {"tool":"scrape_url","args":{"url":"..."}}
event: db_write     data: {"entity_id":"in-premji-invest","provenance":"chat_enriched"}
event: message      data: {"text":"Wrote Premji Invest. 6/7 questions answered."}
event: done         data: {}
```

`GET /api/chat/{session_id}` returns full message history (for refresh resilience).

### System prompt (lives in `prompts.py`)

Single source of truth for the agent's behavior. Includes verbatim:

- Project objective (the 3-line "you are looking for" from the brief)
- The 7 core questions
- The constraints (every claim sourced, no generics, controllers must be named, assumptions explicit)
- Available tools and when to use each
- Output requirement: must call `commit_entity` before claiming success
- Banned phrases list (mirrors validator)

## 3. Backend layout

New files:
- `backend/research/__init__.py`
- `backend/research/tools.py` — tool function implementations + JSON-schema definitions
- `backend/research/prompts.py` — system prompt + extraction templates
- `backend/research/loop.py` — tool-use orchestrator
- `backend/research/session.py` — in-memory session store
- `backend/research/validator.py` — bundle validator
- `backend/routers/chat.py` — `POST /api/chat` (SSE) + `GET /api/chat/{session_id}`

Modified:
- `backend/main.py` — register chat router; deregister ask router
- `backend/db.py` — add `commit_evidence_bundle(bundle)` helper used by the `commit_entity` tool
- `backend/schemas.py` — add `Evidence`, `ResearchBundle` pydantic models; extend `EntityDetail` to include `evidence: list[Evidence]`
- `backend/routers/entity.py` — include evidence rows in detail response
- `backend/llm.py` — replace `MODEL = "owl-alpha"` with `MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")`; add tool-call helper that handles the multi-call loop

Removed:
- `backend/routers/ask.py` (replaced by chat)

Re-added MCP wrappers:
- `ingest/sources/finnhub.py`
- `ingest/sources/polygon.py`

## 4. Seed re-curation (~20 named vehicles)

Discard the 65 current entries (mostly family-named). Curate ~20 well-known specific investment vehicles. Each row gets the full 7-question evidence pass before commit.

Initial list (final selection during execution):

- **India (5):** Premji Invest · Tata Sons · Catamaran Ventures · RNT Associates · Bajaj Holdings & Investment
- **Hong Kong (3):** Horizons Ventures · CK Hutchison Holdings · Henderson Land Development
- **Singapore (2):** Tsao Family Office · Heliconia Capital
- **Indonesia (2):** Sinar Mas Group · Djarum
- **China (2):** Geely Holding Group · Wanda Group
- **South Korea (1):** Samsung C&T
- **Japan (1):** Suntory Holdings
- **Australia (2):** Tattarang · Hancock Prospecting
- **Thailand (1):** Central Group
- **Philippines (1):** Ayala Corporation

Selection criteria (enforced at curation time):
- Must be a named investment vehicle / holding company / SFO / MFO — not a family bucket
- Must have a public website OR public filing disclosing AUM/strategy
- Must have ≥1 named non-family controller (CIO/PM/CEO) findable via Apollo or LinkedIn

Curation tooling: a `scripts/curate_seed.py` that, given a list of `(name, country, type)` tuples, invokes the same `research/loop.py` non-interactively against each and commits as `provenance='curated'`. This both seeds the demo AND smoke-tests the chat pipeline before the demo.

## 5. Frontend changes (minimal)

- New `frontend/src/components/ChatPanel.tsx` — slide-out from right edge (420px), toggle from top-bar icon, message bubbles with inline step badges, no markdown rendering.
- `EntityTable.tsx`: replace `DQ` column with `Evidence` (`N/7` + filled/open dot).
- `DetailView.tsx`: replace current sections with 7 question sections (label + narrative + single `sources: domain (tool)` line each); show `provenance` + `confidence_score` near header.
- `App.tsx`: route the existing ask flow to the new `/api/chat`; persist `session_id` in local state.
- `api.ts`: add `streamChat(session_id, message, on_event)` using a fetch-stream reader.

No other UI changes. The dark theme + Fira Sans/Fira Code typography is unchanged.

## 6. Methodology document updates

`docs/METHODOLOGY.md` rewritten to:
- Replace the listed-discovery + curated-seed narrative with the new pipeline (discovery → scrape → extract → cite → validate → commit)
- Add a "Scaling to paid data" section: each tool's free-tier impl + the paid-tier swap target (PitchBook for search, Bright Data for scrape, ZoomInfo for org lookup, Bloomberg/Refinitiv for fundamentals). Same function signatures, one-file changes per tool.
- Add the validator rules verbatim (the "no generics" contract)
- Add example chat trace (turn → tool calls → DB writes) for the README too

## 7. Verification (end-to-end)

After implementation:

1. `pytest -q` — all existing tests stay green; new tests for the validator (banned phrases, missing sources, etc.) and the migration.
2. Run `scripts/curate_seed.py` against the ~20 seed list with real Exa+Firecrawl+Apollo+Finnhub keys. Confirm DB has 20 entities, ≥5 evidence rows per entity, sources populated, validator never rejected a curator-supplied bundle.
3. `make backend && make frontend`. In the chat panel, ask: "find Vietnamese family offices investing in tech". Confirm SSE events stream in browser DevTools, agent commits ≥1 new entity, new row appears in the browse table, detail view shows all 7 sections.
4. Manual review of 3 random curated entries: every "sources:" link opens to a real page that supports the answer.
5. Rebuild Docker image; refresh path (`docker exec … python scripts/curate_seed.py`) succeeds against the volume DB.

## 8. Out of scope (explicit)

- Chat history persistence beyond session (intentional, matches "no cache/queueing" from original brief)
- Auth / multi-user
- Editing or deleting evidence rows from the UI (read-only display; agent is the only writer)
- Activity timeline upgrades beyond what the agent commits
- Replacing or restyling the existing browse table or dark theme
