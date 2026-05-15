#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout /app/certs/key.pem -out /app/certs/cert.pem \
  -subj "/CN=localhost" -days 365 \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 /app/certs/key.pem
