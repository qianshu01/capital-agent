# Methodology

## Goal
Produce a defensible, repeatable inventory of family-office and family-controlled capital pools across 22 Asian markets.

## Discovery and enrichment

**Curated seed (all tiers, primary source of truth).** `ingest/seeds/private_offices.yaml` lists 65+ known SFOs/MFOs/foundations with a `source_url` and a `note` explaining the AUM basis for each entry. This is the only mandatory step — running without any API keys produces a complete seed-only database.

**Exa discovery pass (`--discover`, optional).** When `EXA_API_KEY` is set, `ingest/sources/exa.py` runs neural web searches for each Tier-1/Tier-2 country (e.g. "family office Singapore 2025"). The top results are written to `data/discovery_candidates.json` for human triage. Candidates are never added to the database automatically — they require a human review step.

**Per-source enrichment pass (`--enrich-sources`, optional).** Four enrichment sources may run against each seed entity:

- **Crunchbase** (`CRUNCHBASE_API_KEY`): organization lookup and recent funding/deal history → `activities` rows and `crunchbase` source rows.
- **Apollo** (`APOLLO_API_KEY`): organization profile → fills missing `sectors`, `employees`, `founded_year` → `apollo` source rows.
- **LinkedIn via Proxycurl** (`LINKEDIN_API_KEY`): company and person profiles for entities with a known LinkedIn URL → `linkedin` source rows.
- **Firecrawl** (`FIRECRAWL_API_KEY`): scrapes each entity's `source_url` to markdown → attaches a text snippet as a `firecrawl` source row.

All enrichment sources fail soft: a missing key or network error logs a single warning and returns an empty result. The build never fails due to enrichment.

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
docker exec capital-agent python -m ingest.run \
  --out /app/data/capital.db [--discover] [--enrich-sources] [--enrich]
```

Backend reads continue uninterrupted thanks to SQLite WAL mode.

## Limits

- The discovery pass (`--discover`) produces candidate URLs only; a human must triage `data/discovery_candidates.json` before those entities enter the database.
- Enrichment sources (Crunchbase, Apollo, LinkedIn, Firecrawl) each require a paid API key; without keys the enrichment step is silently skipped and entities retain their seed-only data quality score.
- Frontier-market depth is explicitly low — Tier-3 country entities are placeholders to ensure regional coverage rather than triage-grade data.
