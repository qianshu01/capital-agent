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
