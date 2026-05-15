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
