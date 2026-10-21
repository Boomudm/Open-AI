#!/usr/bin/env bash
# Mac thin client — Next.js only; API/Celery/DB run on Jetson.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f web/.env.local ]]; then
  if [[ -f web/.env.mac-thin.example ]]; then
    cp web/.env.mac-thin.example web/.env.local
  echo "Created web/.env.local — set SPARK_API_PROXY_TARGET and JWT_SECRET (must match Jetson .env)"
    echo "  Example: SPARK_API_PROXY_TARGET=http://192.168.1.50:8000"
    exit 1
  fi
  die_msg="web/.env.local missing"
  echo "$die_msg"
  exit 1
fi

# Stop local API/Celery if accidentally running (frees Mac RAM)
pkill -f "uvicorn spark.main:app" 2>/dev/null || true
pkill -f "celery -A spark.workers.celery_app worker" 2>/dev/null || true

echo "==> Neo Chat web (thin client) http://127.0.0.1:3000"
echo "    API proxied via SPARK_API_PROXY_TARGET in web/.env.local"
echo "    Stop local Docker infra on Mac if Jetson owns DB: docker compose down"
echo ""

cd web
npm run dev
