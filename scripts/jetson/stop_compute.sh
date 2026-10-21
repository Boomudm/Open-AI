#!/usr/bin/env bash
# Stop API + Celery started by start_compute.sh (or manual runs on Jetson).
set -euo pipefail

pkill -f "uvicorn spark.main:app" 2>/dev/null || true
pkill -f "celery -A spark.workers.celery_app worker" 2>/dev/null || true
echo "[jetson] Stopped API and Celery workers"
