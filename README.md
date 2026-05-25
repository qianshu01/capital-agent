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

Docker (HTTP, port 8000):

```bash
docker build -t capital-agent .
docker run -d --name capital-agent -p 8000:8000 \
  -v capital-data:/app/data \
  --env-file .env \
  capital-agent
open http://localhost:8000
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
