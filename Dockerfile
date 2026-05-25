# Stage 1: Frontend build
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY requirements.txt requirements-ingest.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ingest.txt
COPY backend/ ./backend/
COPY ingest/ ./ingest/
COPY scripts/entrypoint.sh ./
COPY scripts/ ./scripts/
RUN chmod +x ./entrypoint.sh
COPY --from=frontend /fe/dist ./backend/static
COPY seed/capital.db /app/seed/capital.db
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
