#!/usr/bin/env bash
# Start Neo Chat infra without Docker when compose containers are unhealthy (disk-full recovery).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
log() { echo "[local-infra] $*"; }

_pg_ok() {
  PGPASSWORD="${POSTGRES_PASSWORD:-sparkpass}" psql -h 127.0.0.1 -p "$1" -U "${POSTGRES_USER:-spark}" -d "${POSTGRES_DB:-spark_db}" -c "SELECT 1" >/dev/null 2>&1
}

_redis_ok() {
  redis-cli -p "$1" ping >/dev/null 2>&1
}

_qdrant_ok() {
  curl -sf "http://127.0.0.1:$1/" >/dev/null 2>&1
}

# ── Postgres: prefer Docker 5433, fall back to Homebrew 5432 ─────────────────
PG_PORT=5433
if _pg_ok 5433; then
  log "Postgres OK on :5433 (Docker)"
elif _pg_ok 5432; then
  PG_PORT=5432
  log "Postgres OK on :5432 (Homebrew)"
else
  log "Creating spark role/db on Homebrew Postgres :5432..."
  psql -h 127.0.0.1 -p 5432 -d postgres <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'spark') THEN
    CREATE ROLE spark WITH LOGIN PASSWORD 'sparkpass' CREATEDB;
  END IF;
END $$;
SELECT 'CREATE DATABASE spark_db OWNER spark' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'spark_db')\gexec
GRANT ALL PRIVILEGES ON DATABASE spark_db TO spark;
SQL
  PG_PORT=5432
  log "Postgres ready on :5432"
fi

# ── Redis: prefer Docker 6379, fall back to local 6380 ───────────────────────
REDIS_PORT=6379
if ! _redis_ok 6379; then
  REDIS_PORT=6380
  mkdir -p /tmp/redis-spark
  if ! _redis_ok 6380; then
    if ! command -v redis-server >/dev/null 2>&1; then
      log "Installing redis via Homebrew..."
      brew install redis
    fi
    redis-server --port 6380 --daemonize yes --dir /tmp/redis-spark --save "" 2>/dev/null || true
  fi
  log "Redis on :6380 (Docker :6379 unavailable)"
else
  log "Redis OK on :6379"
fi

# ── Qdrant: prefer Docker 6333, fall back to native binary on 6335 ───────────
QDRANT_PORT=6333
if ! _qdrant_ok 6333; then
  QDRANT_PORT=6335
  mkdir -p /tmp/qdrant-storage
  if ! _qdrant_ok 6335; then
    QDRANT_BIN="/tmp/qdrant"
    if [[ ! -x "$QDRANT_BIN" ]]; then
      log "Downloading Qdrant v1.11.3 binary..."
      curl -fsSL -o /tmp/qdrant.tar.gz \
        "https://github.com/qdrant/qdrant/releases/download/v1.11.3/qdrant-aarch64-apple-darwin.tar.gz"
      tar -xzf /tmp/qdrant.tar.gz -C /tmp
    fi
    QDRANT__SERVICE__HTTP_PORT=6335 QDRANT__SERVICE__GRPC_PORT=6336 \
      QDRANT__STORAGE__STORAGE_PATH=/tmp/qdrant-storage \
      nohup "$QDRANT_BIN" > /tmp/qdrant.log 2>&1 &
    sleep 2
  fi
  log "Qdrant on :6335 (Docker :6333 unavailable)"
else
  log "Qdrant OK on :6333"
fi

cat <<EOF

Add to .env (or export):
  POSTGRES_PORT=$PG_PORT
  REDIS_URL=redis://localhost:${REDIS_PORT}/0
  QDRANT_PORT=$QDRANT_PORT

Then: alembic upgrade head && python scripts/ensure_qdrant_indexes.py
EOF
