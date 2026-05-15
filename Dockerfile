# Stage 1: Frontend build
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Ingestion (produces seed DB inside the image)
FROM python:3.12-slim AS ingest
WORKDIR /ingest
COPY ingest/ ./ingest/
COPY requirements-ingest.txt .
RUN pip install --no-cache-dir -r requirements-ingest.txt
ARG POLYGON_API_KEY=""
ARG FINNHUB_API_KEY=""
ARG ALPHAVANTAGE_API_KEY=""
ARG OPENROUTER_API_KEY=""
ARG ENRICH=""
ENV POLYGON_API_KEY=$POLYGON_API_KEY \
    FINNHUB_API_KEY=$FINNHUB_API_KEY \
    ALPHAVANTAGE_API_KEY=$ALPHAVANTAGE_API_KEY \
    OPENROUTER_API_KEY=$OPENROUTER_API_KEY
RUN python -m ingest.run --out /capital.db ${ENRICH:+--enrich}

# Stage 3: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-ingest.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ingest.txt
COPY backend/ ./backend/
COPY ingest/ ./ingest/
COPY scripts/gen-cert.sh scripts/entrypoint.sh ./
RUN chmod +x ./gen-cert.sh ./entrypoint.sh && ./gen-cert.sh
COPY --from=frontend /fe/dist ./backend/static
COPY --from=ingest /capital.db /app/seed/capital.db
VOLUME /app/data
EXPOSE 8443
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/certs/key.pem", \
     "--ssl-certfile", "/app/certs/cert.pem"]
