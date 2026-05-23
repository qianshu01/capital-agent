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
