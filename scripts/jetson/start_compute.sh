#!/usr/bin/env bash
# Start API + Celery on Jetson (foreground logs). Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

[[ -d .venv ]] || { echo "Run ./scripts/jetson/bootstrap_compute.sh first"; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate
set -a
# shellcheck disable=SC1091
source .env
set +a

export PYTHONPATH=src
export PYTHONUNBUFFERED=1
export PYDANTIC_DISABLE_PLUGINS=1
unset SPARK_ALLOW_CPU_RERANK

PIDS=()
cleanup() {
  echo ""
  echo "[jetson] Stopping..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if ! curl -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  echo "[jetson] API http://0.0.0.0:8000"
  uvicorn spark.main:app --host 0.0.0.0 --port 8000 --app-dir src &
  PIDS+=($!)
  for _ in $(seq 1 90); do
    curl -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break
    sleep 2
  done
fi

echo "[jetson] Celery worker (celery + ocr_heavy)"
celery -A spark.workers.celery_app worker \
  --concurrency="${CELERY_CONCURRENCY:-1}" \
  --loglevel=info \
  -Q celery,ocr_heavy &
PIDS+=($!)

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "Jetson compute running."
echo "  healthz: http://${LAN_IP:-localhost}:8000/healthz"
echo "  Mac UI:  SPARK_API_PROXY_TARGET=http://${LAN_IP:-JETSON_IP}:8000 in web/.env.local"
echo ""

wait
