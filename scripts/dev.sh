#!/usr/bin/env bash
# Start local dev stack: docker infra + API + Celery + Next.js (foreground logs).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/env_nvme_cache.sh"

if [[ ! -d .venv ]]; then
  echo "ERROR: .venv missing — run: python3.12 -m venv .venv && pip install -e '.[dev]'"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH=src
export PYDANTIC_DISABLE_PLUGINS=1
export PYTHONUNBUFFERED=1
export SPARK_ALLOW_CPU_RERANK=1

if ! command -v pdfinfo >/dev/null 2>&1; then
  echo "WARN: poppler not found — PDF OCR ingest may fail (brew install poppler)"
fi

echo "==> Docker (postgres, redis, qdrant, minio)..."
docker compose up -d postgres redis qdrant minio minio_init

echo "==> Observability (Prometheus :9090, Grafana :3001)..."
docker compose -f docker-compose.observability.yml up -d prometheus grafana 2>/dev/null || \
  echo "WARN: observability stack failed — App Metrics panel will show Prometheus unreachable"

PIDS=()
cleanup() {
  echo ""
  echo "==> Stopping dev processes..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> API http://127.0.0.1:8000"
python -m uvicorn spark.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src --app-dir src &
PIDS+=($!)

echo "==> Celery worker (celery + ocr_heavy queues, macOS-safe solo pool)"
# PyTorch MPS / Metal cannot be initialized safely in a process forked by
# Celery's default prefork pool on macOS. A solo pool keeps model inference in
# the worker process and prevents objc/MPSGraphObject crashes during ingest.
celery -A spark.workers.celery_app worker --pool=solo --concurrency=1 --loglevel=info -Q celery,ocr_heavy &
PIDS+=($!)

echo "==> Web http://127.0.0.1:3000"
(cd web && npm run dev) &
PIDS+=($!)

echo ""
echo "Login: admin / changeme"
echo "Grafana: http://127.0.0.1:3001/d/spark-overview (admin/admin)"
echo "Press Ctrl+C to stop all services."
echo ""

# macOS ships Bash 3.2 — `wait -n` needs 4.3+
wait
