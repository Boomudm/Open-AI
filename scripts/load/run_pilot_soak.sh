#!/usr/bin/env bash
# Pilot soak runner — ingest + RAG load reports with SLO gate (Phase 15).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DATE_STAMP="${DATE_STAMP:-$(date +%Y%m%d)}"
REPORT_DIR="${REPORT_DIR:-reports/load/${DATE_STAMP}}"
PROFILE="${PROFILE:-configs/load/pilot_profile.yaml}"
DRY_RUN="${DRY_RUN:-1}"

mkdir -p "$REPORT_DIR"

DRY_FLAG=()
if [[ "${DRY_RUN}" == "1" ]]; then
  DRY_FLAG=(--dry-run)
fi

echo "== Ingest soak =="
uv run python scripts/load/soak_ingest.py \
  --profile "$PROFILE" \
  --report "$REPORT_DIR/ingest_soak.json" \
  "${DRY_FLAG[@]}"

echo "== RAG soak =="
uv run python scripts/load/soak_rag.py \
  --profile "$PROFILE" \
  --report "$REPORT_DIR/rag_soak.json" \
  "${DRY_FLAG[@]}"

echo "== Red-team suite size =="
uv run python scripts/validate_redteam_suite.py --min-cases 50

echo "Pilot soak passed (reports=$REPORT_DIR dry_run=$DRY_RUN)"
