# Family Office Capital Agent — Design Spec

**Date:** 2026-05-15
**Status:** Approved (brainstorm → spec)
**Source brief:** `Requirements.md`

## 1. Problem

A fundraising team needs to identify and analyze family-office and family-controlled capital pools across Asia, then prioritise where to spend time. Most attempts fail because they list "rich families" instead of identifiable, accessible **capital pools** with control structures and evidence of investment activity.

The system must:

- Surface specific capital pools (not just family names) across Asia.
- Tie each pool to a control structure and a defensible AUM estimate.
- Cite a source for every material claim.
- Be explorable through a UI that supports both structured filtering and natural-language questions.
- Be reproducible and demoable as a single Docker container over HTTPS.

## 2. Scope decisions (locked during brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Data sourcing | **Hybrid: listed + unlisted, both pre-loaded** | Listed entities discovered via MCP servers; unlisted SFO/MFOs from a curated seed list. MCP-only would miss pure-private FOs; seed-only would be too manual. |
| Geographic coverage | **Tier by data quality** | Tier 1 (HK, JP, SG, IN, KR, AU, CN): full listed-discovery loop. Tier 2 (MY, ID, TH, PH, NZ, VN): listed where MCP permits, plus seed. Tier 3 (Myanmar, Laos, Bhutan, Brunei, Mongolia, Pakistan, Sri Lanka, Bangladesh, Nepal, Cambodia, Kazakhstan): seed-only. |
| LLM role | **In the query path** | A natural-language `/api/ask` endpoint translates questions into filter calls and produces narrative answers. Build-time enrichment of `thesis_blurb` is also LLM-assisted. |
| LLM provider | **OpenRouter, model `owl-alpha`** | Free experimental model, OpenAI-compatible API. Single `OPENROUTER_API_KEY` at runtime. (Implementation note: confirm the exact model slug at OpenRouter — fall back to `openrouter/owl-alpha` or a stable model if `owl-alpha` is renamed/retired.) |
| Data freshness | **Pre-loaded seed + manual refresh via `docker exec`** | Ingestion runs at `docker build` time and ships a seed DB. The DB lives on a writable Docker volume; `docker exec capital-agent python -m ingest.run` re-runs ingestion in place against the live DB. No admin endpoint, no UI button, no scheduler — minimal surface area, easy to undo. |
| Architecture | **Monolithic single container** | One Dockerfile, FastAPI serves both API and React static build, single self-signed cert. Simplest demo footprint. |
| Browse layout | **Dense data table (Bloomberg-style)** | Triage hundreds of entities at once. Click-through opens a richer detail view. |
| Visual style | **Dark Mode (OLED) + Fira Sans / Fira Code** | Matches data-tool conventions; recommended by UX skill for analytics products. |

## 3. High-level architecture

Two phases, fully decoupled:

**Build-time (one-shot ingestion)**

```
ingest/run.py
├── listed_discovery.py     # MCP clients: polygon, finnhub, alpha-vantage
├── private_seed.py         # YAML/JSON of curated SFO/MFO/foundations
├── classify.py             # rules: ownership concentration, family-name match, sector tagging
├── enrich_llm.py           # OpenRouter (optional): thesis_blurb + soft fields
└── write_db.py             # builds /capital.db
```

**Run-time (FastAPI + static React)**

```
backend/
├── main.py                 # FastAPI app, mounts static React build
├── db.py                   # read-only SQLite session
├── routers/
│   ├── entities.py         # GET /api/entities  (filter / browse)
│   ├── entity.py           # GET /api/entities/{id}
│   └── ask.py              # POST /api/ask     (LLM tool-use)
└── llm.py                  # OpenRouter client
frontend/                   # Vite + React + TypeScript + Tailwind
```

**Container exposes 8443 (HTTPS, self-signed).** One process: `uvicorn` serving FastAPI which serves the React build.

**Boundaries:**

- Ingestion never imports backend code; backend never imports ingestion code.
- Network dependencies at runtime: OpenRouter (always, for `/api/ask`); MCP servers (only if `docker exec … ingest.run` is invoked to refresh).
- Backend ↔ Frontend communicate via JSON REST.
- The SQLite DB lives on a Docker volume (`/app/data/capital.db`). Backend opens it in **WAL mode** so reads continue to serve while a refresh writes new rows.

## 4. Data model

Single SQLite database, four tables, kept flat to avoid joins on the hot path. The full data dictionary lives in `docs/DATA.md`.

### `entities` — the core capital pool

```sql
CREATE TABLE entities (
  id              TEXT PRIMARY KEY,            -- slug, e.g. "hk-cheung-kong-holdings"
  name            TEXT NOT NULL,
  type            TEXT NOT NULL,               -- 'listed_holding' | 'sfo' | 'mfo' | 'trust' | 'foundation'
  country         TEXT NOT NULL,               -- ISO 3166-1 alpha-2 ('HK', 'SG', 'IN', ...)
  region          TEXT NOT NULL,               -- 'East Asia' | 'SEA' | 'South Asia' | 'Oceania' | 'Central Asia'
  controlling_family TEXT,
  controllers     TEXT,                        -- JSON array of named individuals
  ticker          TEXT,                        -- listed only
  exchange        TEXT,
  estimated_aum_usd REAL,
  aum_basis       TEXT,                        -- 'market_cap' | 'disclosed' | 'estimate' | 'unknown'
  ownership_pct   REAL,
  sectors         TEXT,                        -- JSON array
  deployment      TEXT,                        -- 'direct' | 'external_managers' | 'mixed' | 'unknown'
  accessibility   TEXT,                        -- 'open' | 'restricted' | 'closed' | 'unknown'
  thesis_blurb    TEXT,                        -- LLM-generated, 1–2 sentences
  data_quality    INTEGER NOT NULL,            -- 1–5 (see "Data-quality scoring" below)
  updated_at      TEXT NOT NULL                -- ISO timestamp
);
CREATE INDEX idx_entities_country ON entities(country);
CREATE INDEX idx_entities_type    ON entities(type);
CREATE INDEX idx_entities_aum     ON entities(estimated_aum_usd);
```

### `sources` — provenance for every material claim

```sql
CREATE TABLE sources (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  field       TEXT NOT NULL,                   -- e.g. 'estimated_aum_usd'
  source_type TEXT NOT NULL,                   -- 'mcp:polygon' | 'mcp:finnhub' | 'filing' | 'news' | 'curated' | 'llm:openrouter'
  url         TEXT,
  note        TEXT,
  retrieved_at TEXT NOT NULL
);
CREATE INDEX idx_sources_entity ON sources(entity_id);
```

### `activities` — recent investment activity

```sql
CREATE TABLE activities (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  date        TEXT,                            -- YYYY-MM-DD
  kind        TEXT NOT NULL,                   -- 'deal' | 'exit' | 'fund_commitment' | 'allocation_change'
  description TEXT NOT NULL,
  source_url  TEXT
);
CREATE INDEX idx_activities_entity ON activities(entity_id);
```

### `assumptions` — explicit estimation logic

```sql
CREATE TABLE assumptions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   TEXT NOT NULL REFERENCES entities(id),
  text        TEXT NOT NULL                    -- e.g. "AUM estimated as 60% of market cap based on disclosed family stake"
);
```

**Why these tables:**

- `entities` alone serves the listing/filter UI — no joins on the hot path.
- `sources` enforces the requirement that every material claim be backed by a source.
- `assumptions` makes estimation logic explicit and reviewable.
- `activities` populates the "currently deployed" and "recent moves" answers.

**Data-quality scoring (1–5):**

- **5** — disclosed AUM (filings or office-published) + named controllers + ≥1 sourced activity in last 24 months.
- **4** — market-cap-derived AUM + named controllers + ≥1 sourced activity.
- **3** — market-cap-derived OR estimated AUM + named family but no individual controllers + sector tags only.
- **2** — estimated AUM + family identifier only (no individuals) + no recent activity.
- **1** — placeholder / known-of entry, AUM unknown.

## 5. Ingestion pipeline

Runs at `docker build` time (producing a seed DB shipped in the image) **and** can be re-run at runtime via `docker exec capital-agent python -m ingest.run --out /app/data/capital.db [--enrich]`. Idempotent given fixed inputs.

**Layout**

```
ingest/
├── run.py                      # orchestrator
├── config.yaml                 # tier-1/2/3 country lists, ownership thresholds, family-name dictionaries
├── seeds/
│   ├── private_offices.yaml    # curated SFOs/MFOs/foundations
│   └── known_families.yaml     # known controlling-family names per country
├── sources/
│   ├── exa.py                  # neural web search (EXA_API_KEY)
│   ├── firecrawl.py            # URL scraping → markdown (FIRECRAWL_API_KEY)
│   ├── crunchbase.py           # org lookup + recent deals (CRUNCHBASE_API_KEY)
│   ├── apollo.py               # org + key-contact lookup (APOLLO_API_KEY)
│   └── linkedin.py             # Proxycurl-based person/company profiles (LINKEDIN_API_KEY)
├── classify.py
├── enrich_llm.py               # gated by --enrich
├── write_db.py
└── snapshot.json               # intermediate cache; lets dev re-runs skip slow API calls
```

**Stages**

1. **Seed load** — primary source of truth. Read `seeds/private_offices.yaml` (65+ curated SFOs/MFOs/foundations), normalize, dedupe on `(country, controlling_family)`.
2. **Optional discovery pass (`--discover`, requires `EXA_API_KEY`)** — for each Tier-1/Tier-2 country, run several Exa neural web searches (e.g. "family office Singapore 2025"). Top results are logged to `data/discovery_candidates.json` for human triage. They do **not** become entities automatically.
3. **Optional per-source enrichment pass (`--enrich-sources`)** — for each seed entity:
   - `CRUNCHBASE_API_KEY` set: `crunchbase.find_org` + `crunchbase.recent_deals` → write `activities` rows + a `crunchbase` source row.
   - `APOLLO_API_KEY` set: `apollo.org_lookup` → fill missing `sectors`/`employees` fields, write `apollo` source row.
   - `LINKEDIN_API_KEY` set and entity has a known LinkedIn URL: `linkedin.company_profile` → enrich sector/country, write `linkedin` source row.
   - `FIRECRAWL_API_KEY` set and entity has a `source_url`: scrape it, attach snippet to a `firecrawl` source row.
4. **LLM enrichment (gated `--enrich`)** — one OpenRouter call per surviving entity to generate `thesis_blurb` and fill missing soft fields (`deployment`, `accessibility`). Cached in `snapshot.json` so repeat builds skip the call.
5. **Source attribution** — every field write also writes a `sources` row.
6. **Write to SQLite** — drop & rebuild `capital.db`. Build fails if entity count below a sanity threshold (default 50).

All source wrappers fail soft: if an API key is missing or a network call fails, a one-line warning is logged and the wrapper returns an empty result. The build never fails due to an enrichment source being unavailable.

**Tier handling**

- Tier 1 (HK, JP, SG, IN, KR, AU, CN): seed + full discovery/enrichment coverage.
- Tier 2 (MY, ID, TH, PH, NZ, VN): seed + discovery where Exa has coverage.
- Tier 3 (Myanmar, Laos, Bhutan, Brunei, Mongolia, Pakistan, Sri Lanka, Bangladesh, Nepal, Cambodia, Kazakhstan): seed-only.

**Failure modes**

- API key missing → log warning, skip that source, do not fail the build.
- LLM enrichment failure → entity still written; `thesis_blurb` left null.
- Empty discovery result → logged; no impact on entity count.

## 6. Backend API

Three endpoints — keep the surface small.

### `GET /api/entities` — structured filter / browse

Query params (all optional, AND-combined):

```
country=HK,SG          # comma-sep ISO codes
region=East Asia
type=sfo,mfo,listed_holding
sector=real_estate
min_aum_usd=500000000
max_aum_usd=
controlling_family=    # substring match
q=                     # free-text over name + controlling_family
sort=aum_desc          # aum_desc | aum_asc | name | data_quality_desc
limit=50, offset=0
```

Returns `{ total, results: [Entity, ...] }`. Pure SQL; no LLM.

### `GET /api/entities/{id}` — detail view

Returns full entity + all `sources`, `activities`, `assumptions`. Pure SQL.

### `POST /api/ask` — natural-language query

Body: `{ "question": "Indian family offices active in renewable energy" }`.

Server runs an LLM tool-use loop with **one tool**: `query_entities(filters_json)` (a thin wrapper over `/api/entities`).

Loop:

1. Send question + system prompt to OpenRouter (`owl-alpha`).
2. LLM emits a `query_entities` tool call → server runs the filter, returns matching IDs + summary fields.
3. LLM emits a final natural-language answer plus `cited_entity_ids: [...]`.
4. Server returns `{ answer, entities: [Entity, ...], filters_used: {...} }`.

Frontend renders the answer text, then the cited entities as table rows beneath. `filters_used` is shown as removable chips so the user understands what the LLM chose.

## 7. Frontend

React + Vite + TypeScript + Tailwind. Single-page app, three views.

**Design system (from UX skill):**

- Style: Dark Mode (OLED) — background `#020617`, primary `#0F172A`, accent `#22C55E`, text `#F8FAFC`.
- Typography: Fira Sans (body), Fira Code (numerics, monospace).
- Vector icons (Lucide); no emojis as icons.
- Min 16px body text, focus rings visible, `prefers-reduced-motion` respected.

**Views:**

1. **Browse view (default)** — dense data table layout (Bloomberg-style).
   - Top: NL search bar ("Ask about Asian family offices…").
   - Left: filter panel (country grouped by region, type, sector, AUM slider).
   - Center: sortable table with columns `Name | Country | Type | Family | AUM | DQ`. AUM column uses Fira Code monospace and is right-aligned.
   - Sort dropdown above the table; column headers also sortable.

2. **Ask view (triggered by NL search)** — same shell, but center-top shows the LLM answer + `filters_used` chips, then the cited entities table.

3. **Detail view (click row)** — replaces center column. Card-style profile header (name, country, family, AUM with basis), then sources table, activities timeline, assumptions list.

**Tech notes:**

- TanStack Query for caching `/api/entities` calls during a session.
- Local component state — no Redux/Zustand.
- ~6–8 components total.

## 8. Container & deployment

Single multi-stage Dockerfile.

```dockerfile
# Stage 1: Frontend build
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Ingestion
FROM python:3.12-slim AS ingest
WORKDIR /ingest
COPY ingest/ ./
COPY requirements-ingest.txt .
RUN pip install --no-cache-dir -r requirements-ingest.txt
ARG POLYGON_API_KEY
ARG FINNHUB_API_KEY
ARG ALPHAVANTAGE_API_KEY
ARG OPENROUTER_API_KEY
ARG ENRICH=false
RUN python run.py --out /capital.db ${ENRICH:+--enrich}

# Stage 3: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY backend/ ./backend/
COPY ingest/ ./ingest/
COPY requirements.txt requirements-ingest.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ingest.txt
COPY --from=frontend /fe/dist ./backend/static
COPY --from=ingest /capital.db /app/seed/capital.db   # seed DB lives in image
COPY scripts/gen-cert.sh scripts/entrypoint.sh ./
RUN ./gen-cert.sh
VOLUME /app/data                                       # writable mount for live DB
EXPOSE 8443
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/certs/key.pem", \
     "--ssl-certfile", "/app/certs/cert.pem"]
```

**`entrypoint.sh`:** if `/app/data/capital.db` is missing or empty, copies `/app/seed/capital.db` over to it; then `exec "$@"` to hand off to the uvicorn `CMD`. This ensures a fresh container always has a working DB on first run, but a re-mounted volume preserves any refreshed state.

**HTTPS:** self-signed cert generated at image build (`gen-cert.sh`). Browsers will show a one-time warning. Cert covers `localhost` + `127.0.0.1`.

**Required env vars at runtime:**
- Always: `OPENROUTER_API_KEY` (for `/api/ask`).
- For `docker exec … ingest.run` refresh with enrichment: `EXA_API_KEY`, `FIRECRAWL_API_KEY`, `CRUNCHBASE_API_KEY`, `APOLLO_API_KEY`, `LINKEDIN_API_KEY`. All are optional — missing keys are skipped gracefully.

**Required env vars at build:** none mandatory (seed-only DB builds without any keys). Pass source keys as `--build-arg` to enable enrichment at build time. `OPENROUTER_API_KEY` only if `ENRICH=true`.

**Local dev (no Docker):**

```
make ingest          # runs ingestion → ./data/capital.db
make backend         # uvicorn dev server on :8000
make frontend        # vite dev server on :5173, proxies /api → :8000
```

**Run the demo:**

```
docker build \
  --build-arg EXA_API_KEY=$EXA_API_KEY \
  --build-arg FIRECRAWL_API_KEY=$FIRECRAWL_API_KEY \
  --build-arg CRUNCHBASE_API_KEY=$CRUNCHBASE_API_KEY \
  --build-arg APOLLO_API_KEY=$APOLLO_API_KEY \
  --build-arg LINKEDIN_API_KEY=$LINKEDIN_API_KEY \
  -t capital-agent .

docker run -d --name capital-agent \
  -p 8443:8443 \
  -v capital-data:/app/data \
  -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY \
  -e EXA_API_KEY=$EXA_API_KEY \
  -e FIRECRAWL_API_KEY=$FIRECRAWL_API_KEY \
  -e CRUNCHBASE_API_KEY=$CRUNCHBASE_API_KEY \
  -e APOLLO_API_KEY=$APOLLO_API_KEY \
  -e LINKEDIN_API_KEY=$LINKEDIN_API_KEY \
  capital-agent
# → open https://localhost:8443
```

**Refresh the dataset (occasional):**

```
docker exec capital-agent python -m ingest.run \
  --out /app/data/capital.db [--discover] [--enrich-sources] [--enrich]
# Backend stays up; new rows visible on the next query.
```

## 9. Repository layout

```
.
├── README.md
├── Dockerfile
├── Makefile
├── docs/
│   ├── DATA.md                      # data dictionary (every table & field, plain-language)
│   ├── METHODOLOGY.md               # how the dataset is built; defensible methodology write-up
│   └── superpowers/specs/...        # design + future specs
├── ingest/
│   ├── run.py
│   ├── config.yaml
│   ├── seeds/
│   ├── sources/
│   ├── classify.py
│   ├── enrich_llm.py
│   └── write_db.py
├── backend/
│   ├── main.py
│   ├── db.py
│   ├── routers/
│   ├── llm.py
│   └── static/                       # populated at build time
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
├── scripts/
│   └── gen-cert.sh
└── data/                             # gitignored; populated at build time
```

## 10. Testing

Light, demo-grade.

- `ingest/`: pytest unit tests for `classify.py` rules and `write_db.py` schema.
- `backend/`: integration tests for the three endpoints against a fixture SQLite DB.
- `frontend/`: 1–2 component tests for filter logic; manual smoke checklist for visuals.
- `/api/ask`: mocked OpenRouter responses in tests; manual end-to-end check before demo.

## 11. Deliverables (mapped to the brief)

| Brief asks for | Delivered as |
|---|---|
| Structured Output | `capital.db` (SQLite), schema documented in `docs/DATA.md` |
| Exploration Layer | React frontend with table browse, filters, NL ask, detail view |
| Insight | Sortable AUM/data-quality columns + thesis blurbs + `filters_used` chips on NL answers |
| Methodology (repeatable, scalable) | `docs/METHODOLOGY.md` + `ingest/` pipeline that re-runs deterministically |
| Sources for every material claim | `sources` table; surfaced in detail view |
| Explicit assumptions | `assumptions` table; surfaced in detail view |
| Coverage across Asia | Tiered ingestion + seed list across all 22 listed countries |

## 12. Open items / out of scope

- Authentication: none (demo only). The `docker exec` refresh path implicitly assumes the operator has shell access to the host.
- Multi-user state: none.
- Admin HTTP endpoint for refresh: out of scope (use `docker exec`).
- Scheduled refresh / cron: out of scope.
- CA-signed HTTPS: out of scope; self-signed only.
- Caching/queueing/observability beyond build-report logs: out of scope.
- Frontier-market depth: explicitly accepted as low; entity list will note "no MCP coverage" for Tier-3 markets.
