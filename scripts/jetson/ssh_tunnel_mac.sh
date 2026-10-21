#!/usr/bin/env bash
# Forward Jetson API (:8000) to Mac localhost — use with web/.env.local → 127.0.0.1:8000
set -euo pipefail

JETSON_HOST="${JETSON_HOST:-10.11.98.156}"
JETSON_USER="${JETSON_USER:-jetson}"
LOCAL_PORT="${LOCAL_PORT:-8000}"
REMOTE_PORT="${REMOTE_PORT:-8000}"

echo "==> SSH tunnel: localhost:${LOCAL_PORT} → ${JETSON_USER}@${JETSON_HOST}:${REMOTE_PORT}"
echo "    Keep this terminal open. In another terminal:"
echo "      cd web && npm run dev"
echo "    web/.env.local should use:"
echo "      SPARK_API_PROXY_TARGET=http://127.0.0.1:${LOCAL_PORT}"
echo ""
echo "    Test: curl http://127.0.0.1:${LOCAL_PORT}/healthz"
echo ""

exec ssh -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
  "${JETSON_USER}@${JETSON_HOST}"
