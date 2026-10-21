#!/usr/bin/env bash
# Jetson compute bootstrap: Docker infra + venv + DB migrate + Qdrant indexes.
# Run ON THE JETSON from repo root after install_prereqs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/env_nvme_cache.sh"

log() { echo "[jetson-bootstrap] $*"; }
die() { echo "[jetson-bootstrap] ERROR: $*" >&2; exit 1; }

[[ "$(uname -m)" == "aarch64" ]] || die "This script targets Jetson (aarch64)"

# ── 1. Env ───────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  cp deploy/jetson/.env.jetson.example .env
  log "Created .env — set OLLAMA_API_KEY before starting compute"
fi

if grep -q 'REPLACE_WITH_YOUR_GATEWAY_KEY' .env 2>/dev/null; then
  log "WARN: OLLAMA_API_KEY still placeholder in .env"
fi

# ── 2. Docker infra ──────────────────────────────────────────────────────────
log "Starting postgres, redis, qdrant, minio..."
docker compose up -d postgres redis qdrant minio minio_init

for i in $(seq 1 60); do
  if PGPASSWORD=sparkpass psql -h 127.0.0.1 -p 5433 -U spark -d spark_db -c "SELECT 1" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
PGPASSWORD=sparkpass psql -h 127.0.0.1 -p 5433 -U spark -d spark_db -c "SELECT 1" >/dev/null \
  || die "Postgres not ready on :5433"

# ── 3. Python venv ───────────────────────────────────────────────────────────
PY=python3.12
command -v "$PY" >/dev/null || PY=python3
command -v "$PY" >/dev/null || die "python3.12+ required"

if [[ ! -d .venv ]]; then
  log "Creating .venv..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH=src

pip install -q --upgrade pip
pip install -q -e ".[dev]"

# ── 4. Jetson PyTorch (CUDA for bge-m3 + rerank) ─────────────────────────────
"$ROOT/scripts/jetson/install_pytorch.sh"

# ── 5. DB + indexes ──────────────────────────────────────────────────────────
alembic upgrade head
python scripts/init_db.py 2>/dev/null || true
python scripts/ensure_qdrant_indexes.py 2>/dev/null || true

# ── 6. JWT secret if still default ───────────────────────────────────────────
if grep -q 'JWT_SECRET=change-me-on-jetson' .env 2>/dev/null; then
  SECRET="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p)"
  if [[ -n "$SECRET" ]]; then
    sed -i.bak "s/^JWT_SECRET=.*/JWT_SECRET=${SECRET}/" .env && rm -f .env.bak
    log "Generated JWT_SECRET in .env — copy same value to Mac web/.env.local if using JWT middleware"
  fi
fi

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
log "Bootstrap complete."
echo "  LAN IP (guess): ${LAN_IP:-unknown}"
echo "  Next on Jetson:  ./scripts/jetson/start_compute.sh"
echo "  On Mac:          cp web/.env.mac-thin.example web/.env.local"
echo "                   # edit SPARK_API_PROXY_TARGET=http://${LAN_IP:-JETSON_IP}:8000"
echo "                   ./scripts/mac_dev_thin.sh"
echo ""
echo "  Fresh demo data: python scripts/seed_customer_demo.py --reset --ingest"
echo "  Migrate Mac DB:  ./scripts/jetson/migrate_export_mac.sh  (on Mac)"
