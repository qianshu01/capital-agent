#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/data
echo "[entrypoint] seeding /app/data/capital.db from image (overwrite)"
cp /app/seed/capital.db /app/data/capital.db
export DB_PATH=/app/data/capital.db
exec "$@"
