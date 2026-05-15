#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/data
if [[ ! -s /app/data/capital.db ]]; then
  echo "[entrypoint] seeding /app/data/capital.db from image"
  cp /app/seed/capital.db /app/data/capital.db
fi
export DB_PATH=/app/data/capital.db
exec "$@"
