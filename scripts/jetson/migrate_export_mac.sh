#!/usr/bin/env bash
# Export Postgres + Qdrant + data dirs from Mac Docker stack for Jetson import.
# Run ON THE MAC from repo root (infra must be up).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

OUT="${1:-./deploy/jetson/migration_bundle}"
mkdir -p "$OUT"

log() { echo "[migrate-export] $*"; }
die() { echo "[migrate-export] ERROR: $*" >&2; exit 1; }

docker ps --format '{{.Names}}' | grep -q spark_postgres || die "spark_postgres not running — start: docker compose up -d"

log "Dumping Postgres..."
docker exec spark_postgres pg_dump -U spark -d spark_db --no-owner --no-acl \
  | gzip -9 > "$OUT/postgres.sql.gz"

if docker ps --format '{{.Names}}' | grep -q spark_qdrant; then
  log "Qdrant snapshot (collections list)..."
  curl -sf "http://localhost:6333/collections" -o "$OUT/qdrant_collections.json" || true
  log "For full Qdrant migrate: stop qdrant, tar volume spark_qdrant_data, copy to Jetson"
fi

log "Archiving data/ (documents, inbox)..."
tar -czf "$OUT/data.tar.gz" data 2>/dev/null || log "WARN: data/ missing or empty"

log "Bundle: $OUT"
ls -lh "$OUT"
echo ""
echo "Copy to Jetson:"
echo "  scp -r $OUT <user>@<jetson-ip>:~/spark/deploy/jetson/"
echo "Then on Jetson: ./scripts/jetson/migrate_import_jetson.sh"
