#!/usr/bin/env bash
# Import migration bundle produced by migrate_export_mac.sh — run ON JETSON.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BUNDLE="${1:-./deploy/jetson/migration_bundle}"
die() { echo "[migrate-import] ERROR: $*" >&2; exit 1; }
log() { echo "[migrate-import] $*"; }

[[ -f "$BUNDLE/postgres.sql.gz" ]] || die "Missing $BUNDLE/postgres.sql.gz — run migrate_export_mac.sh on Mac first"

docker compose up -d postgres redis qdrant minio minio_init
sleep 5

log "Restoring Postgres (replaces spark_db)..."
docker exec -i spark_postgres psql -U spark -d postgres -v ON_ERROR_STOP=1 <<-SQL
DROP DATABASE IF EXISTS spark_db WITH (FORCE);
CREATE DATABASE spark_db OWNER spark;
SQL
gunzip -c "$BUNDLE/postgres.sql.gz" | docker exec -i spark_postgres psql -U spark -d spark_db -v ON_ERROR_STOP=1

if [[ -f "$BUNDLE/data.tar.gz" ]]; then
  log "Restoring data/..."
  tar -xzf "$BUNDLE/data.tar.gz" -C "$ROOT"
fi

# shellcheck disable=SC1091
[[ -d .venv ]] && source .venv/bin/activate
export PYTHONPATH=src
python scripts/ensure_qdrant_indexes.py 2>/dev/null || true

log "Import done. Start compute: ./scripts/jetson/start_compute.sh"
log "NOTE: Qdrant vectors are NOT in postgres dump — if collections differ, re-ingest or copy qdrant volume from Mac"
