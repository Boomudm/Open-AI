#!/usr/bin/env bash
# Restore from a dated snapshot:
#   ./ops/restore.sh 20260524T180000Z
set -euo pipefail

TS=${1:?usage: restore.sh <TIMESTAMP>}
ROOT=${BACKUP_ROOT:-/var/backups/spark}
PG_USER=${POSTGRES_USER:-spark}
PG_DB=${POSTGRES_DB:-spark_db}

DUMP="$ROOT/postgres/${PG_DB}_${TS}.sql.gz"
[[ -f "$DUMP" ]] || { echo "missing dump: $DUMP"; exit 1; }

echo "[$(date -u)] dropping current schema and reloading"
docker exec -i spark_postgres dropdb -U "$PG_USER" --if-exists "$PG_DB"
docker exec -i spark_postgres createdb -U "$PG_USER" "$PG_DB"
gunzip -c "$DUMP" | docker exec -i spark_postgres psql -U "$PG_USER" -d "$PG_DB"

QSNAP="$ROOT/qdrant/snap_${TS}"
if [[ -d "$QSNAP" ]]; then
  echo "[$(date -u)] restoring qdrant snapshot"
  docker cp "$QSNAP" spark_qdrant:/qdrant/storage/snapshots/
  curl -sf -X PUT "http://localhost:6333/collections/spark_docs/snapshots/recover" \
    -H 'Content-Type: application/json' \
    -d "{\"location\":\"file:///qdrant/storage/snapshots/snap_${TS}\"}"
fi

echo "[$(date -u)] restore_complete"
