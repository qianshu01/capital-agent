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
