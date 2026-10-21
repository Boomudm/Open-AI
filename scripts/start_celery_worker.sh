#!/usr/bin/env bash
# Start Celery worker + beat locally (when Docker factory compose unavailable).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/src"
source "$ROOT/.venv/bin/activate"
exec celery -A spark.workers.celery_app worker --loglevel=info
