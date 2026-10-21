#!/usr/bin/env bash
# Daily backup of Postgres + Qdrant + raw documents.
# Cron suggestion (UTC):  10 18 * * *  /opt/spark/ops/backup.sh
set -euo pipefail

TS=$(date -u +%Y%m%dT%H%M%SZ)
ROOT=${BACKUP_ROOT:-/var/backups/spark}
PG_USER=${POSTGRES_USER:-spark}
PG_DB=${POSTGRES_DB:-spark_db}
QDRANT_URL=${QDRANT_URL:-http://localhost:6333}
SPARK_DATA=${SPARK_DATA:-/opt/spark/data/raw}

mkdir -p "$ROOT/postgres" "$ROOT/qdrant" "$ROOT/raw"

echo "[$(date -u)] backup_postgres start"
docker exec spark_postgres pg_dump -U "$PG_USER" -d "$PG_DB" \
  | gzip > "$ROOT/postgres/${PG_DB}_${TS}.sql.gz"
echo "[$(date -u)] backup_postgres done"

echo "[$(date -u)] backup_qdrant start"
SNAP_NAME="snap_${TS}"
curl -sf -X POST "$QDRANT_URL/snapshots" -H 'Content-Type: application/json' \
  -d "{\"name\":\"$SNAP_NAME\"}" > /dev/null
docker cp "spark_qdrant:/qdrant/storage/snapshots/$SNAP_NAME" "$ROOT/qdrant/$SNAP_NAME" \
  || echo "WARN: qdrant snapshot copy failed; check storage path"
echo "[$(date -u)] backup_qdrant done"

echo "[$(date -u)] rsync_raw start"
rsync -a --delete "$SPARK_DATA/" "$ROOT/raw/"
echo "[$(date -u)] rsync_raw done"

# retention: keep 14 daily snapshots
find "$ROOT/postgres" -name "*.sql.gz" -mtime +14 -delete || true
find "$ROOT/qdrant"   -maxdepth 1 -mindepth 1 -mtime +14 -exec rm -rf {} + || true

echo "[$(date -u)] backup_complete"
