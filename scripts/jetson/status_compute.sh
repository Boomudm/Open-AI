#!/usr/bin/env bash
# Quick health check — run on Jetson or from Mac (set JETSON_HOST).
set -euo pipefail

HOST="${JETSON_HOST:-127.0.0.1}"
API="http://${HOST}:8000"

echo "==> API $API"
curl -sf "$API/healthz" && echo "" || echo "FAIL healthz"
curl -sf "$API/readyz" | head -c 400 && echo "" || echo "FAIL readyz (may be warming up)"

echo "==> Docker infra"
docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null | grep -E 'spark_|NAMES' || echo "docker not running"

if [[ "$(uname -m)" == "aarch64" ]] && [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate 2>/dev/null || true
  python -c "
import torch
print('torch cuda:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')
" 2>/dev/null || echo "torch: not installed"
fi

if command -v celery >/dev/null 2>&1; then
  PYTHONPATH=src celery -A spark.workers.celery_app inspect ping 2>/dev/null | head -3 || echo "celery: no workers"
fi
