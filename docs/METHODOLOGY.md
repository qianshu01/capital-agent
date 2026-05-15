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
