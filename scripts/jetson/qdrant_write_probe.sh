#!/usr/bin/env bash
# Qdrant WRITE-path health probe with auto-restart.
#
# Why: the qdrant update worker has died twice in two days (16-17 Jul 2026)
# with reads still healthy — every upsert fails "Can't reach one of the
# workers: channel closed", ingest jobs fail, and the container healthcheck
# (read-only) stays green. A `docker restart spark_qdrant` fixes it.
#
# This probe upserts a fixed point into a dedicated 1-dim `_health_probe`
# collection with ?wait=true (forces the write pipeline). After
# $FAILS_BEFORE_RESTART consecutive failures it restarts the container —
# consecutive, so a transient timeout during heavy ingest doesn't bounce a
# healthy instance.
#
# Install (jetson user, docker group, no sudo needed):
#   (crontab -l 2>/dev/null; echo '*/2 * * * * /mnt/nvme-data/spark-1/scripts/jetson/qdrant_write_probe.sh') | crontab -
set -u

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION="_health_probe"
STATE_DIR="${HOME}/.local/state/spark"
STATE_FILE="${STATE_DIR}/qdrant_probe_fails"
LOG_FILE="${STATE_DIR}/qdrant_probe.log"
FAILS_BEFORE_RESTART="${FAILS_BEFORE_RESTART:-2}"
CURL="curl -s -m 8"
DOCKER_BIN="$(command -v docker || echo /usr/bin/docker)"

mkdir -p "${STATE_DIR}"
log() { echo "$(date -Is) $*" >> "${LOG_FILE}"; }

# Ensure probe collection exists (idempotent; 1-dim to stay negligible).
${CURL} -o /dev/null -X PUT "${QDRANT_URL}/collections/${COLLECTION}" \
  -H 'Content-Type: application/json' \
  -d '{"vectors":{"size":1,"distance":"Dot"}}' 2>/dev/null

RESP=$(${CURL} -X PUT "${QDRANT_URL}/collections/${COLLECTION}/points?wait=true" \
  -H 'Content-Type: application/json' \
  -d '{"points":[{"id":1,"vector":[0.5],"payload":{"probe":true}}]}' 2>&1)

if echo "${RESP}" | grep -q '"status":"ok"'; then
  if [ -s "${STATE_FILE}" ] && [ "$(cat "${STATE_FILE}")" != "0" ]; then
    log "write path recovered (${RESP})"
  fi
  echo 0 > "${STATE_FILE}"
  exit 0
fi

FAILS=$(( $(cat "${STATE_FILE}" 2>/dev/null || echo 0) + 1 ))
echo "${FAILS}" > "${STATE_FILE}"
log "write probe FAILED (${FAILS}/${FAILS_BEFORE_RESTART}): ${RESP:0:200}"

if [ "${FAILS}" -ge "${FAILS_BEFORE_RESTART}" ]; then
  log "restarting spark_qdrant (write path dead)"
  "${DOCKER_BIN}" restart spark_qdrant >> "${LOG_FILE}" 2>&1
  echo 0 > "${STATE_FILE}"
fi
