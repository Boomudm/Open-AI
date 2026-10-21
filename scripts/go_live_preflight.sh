#!/usr/bin/env bash
# Go-live preflight v3 — cutover artifact verification (Phase 16).
#
# Usage:
#   ./scripts/go_live_preflight.sh              # dry-run (structure + gates)
#   ./scripts/go_live_preflight.sh --v3 --strict  # pre-cutover (requires eval reports)
#   ./scripts/go_live_preflight.sh --v3 --strict --skip-eval  # CI gate (no eval run)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }

V3=1
STRICT=0
SKIP_EVAL=0

for arg in "$@"; do
  case "$arg" in
    --v3) V3=1 ;;
    --strict) STRICT=1 ;;
    --skip-eval) SKIP_EVAL=1 ;;
    -h|--help)
      echo "Usage: $0 [--v3] [--strict] [--skip-eval]"
      exit 0
      ;;
    *)
      fail "unknown argument: $arg (use --v3 --strict [--skip-eval])"
      ;;
  esac
done

GIT_SHA="${GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo local)}"
REPORT_DIR="${REPORT_DIR:-reports/eval/${GIT_SHA}}"
CUTOVER_DATE="${CUTOVER_DATE:-$(date +%Y%m%d)}"

echo "== Go-live preflight v3 (strict=${STRICT} skip_eval=${SKIP_EVAL}) =="

required_files=(
  "docs/runbooks/factory_pilot_cutover.md"
  "docs/runbooks/cutover_checklist_v3.md"
  "docs/architecture/import_spine_v2.md"
  "docs/architecture/hybrid_retrieval_v2.md"
  "docs/runbooks/audit_export.md"
  "docs/runbooks/ingest_dlq.md"
  "docs/postmortem/template.md"
  "configs/eval/production_lock_v3.json"
  "configs/production_lock_v3.yaml"
  "configs/load/pilot_profile.yaml"
  "docs/runbooks/templates/pilot_soak_signoff.md"
  "ops/grafana/dashboards/rag_slo.json"
  "ops/prometheus/alerts/rag_v2.yaml"
  "scripts/qdrant_recreate_collections.py"
  "scripts/full_reingest_v2_sparse.py"
  "scripts/wait_ingest_idle.py"
  "scripts/release_gate.sh"
  "scripts/evaluate_baseline.sh"
  "scripts/validate_production_lock_v3.py"
  "scripts/validate_compliance_taxonomy.py"
  "scripts/verify_config_contract.py"
  "scripts/validate_redteam_suite.py"
  "scripts/load/run_pilot_soak.sh"
  "scripts/archive_cutover_reports.sh"
  "scripts/rollback_generation_pin.py"
  "scripts/issue_eval_token.py"
)

for path in "${required_files[@]}"; do
  [[ -f "$path" ]] || fail "missing $path"
done

legacy_locks=(
  "configs/eval/production_lock.json"
  "configs/evaluation_baseline_lock_production.json"
)
for path in "${legacy_locks[@]}"; do
  [[ -f "$path" ]] && fail "legacy v1 lock still present: $path (remove before cutover)"
done

if grep -qE '(^|[[:space:]])scripts/full_reingest\.py|full_reingest\.py --' scripts/go_live_preflight.sh 2>/dev/null; then
  fail "go_live_preflight.sh must not invoke non-sparse full_reingest.py"
fi

echo "== Phase 15 gate =="
uv run python scripts/remediation_v3_phase_gate.py --phase 15 --strict --skip-contracts

echo "== Production lock v3 =="
uv run python scripts/validate_production_lock_v3.py \
  --lock configs/eval/production_lock_v3.json

echo "== Compliance taxonomy =="
uv run python scripts/validate_compliance_taxonomy.py --strict

echo "== Config contract sync =="
uv run python scripts/verify_config_contract.py

echo "== Red-team suite =="
uv run python scripts/validate_redteam_suite.py --min-cases 50

if [[ "${SKIP_EVAL}" == "0" ]]; then
  if [[ ! -d "$REPORT_DIR" ]] || ! compgen -G "$REPORT_DIR/*.json" > /dev/null; then
    if [[ "${STRICT}" == "1" ]]; then
      echo "== Eval suite (required in --strict) =="
      bash scripts/evaluate_baseline.sh
    else
      echo "NOTE: no eval reports at $REPORT_DIR — run scripts/evaluate_baseline.sh before cutover"
    fi
  fi
fi

if [[ -d "$REPORT_DIR" ]] && compgen -G "$REPORT_DIR/*.json" > /dev/null; then
  echo "== Eval outcome gate (strict) =="
  uv run python scripts/validate_production_lock_v3.py \
    --lock configs/eval/production_lock_v3.json \
    --report-dir "$REPORT_DIR" \
    --strict
  echo "== Archive cutover evidence =="
  REPORT_DIR="$REPORT_DIR" CUTOVER_DATE="$CUTOVER_DATE" bash scripts/archive_cutover_reports.sh
elif [[ "${STRICT}" == "1" && "${SKIP_EVAL}" == "0" ]]; then
  fail "strict preflight requires eval reports at $REPORT_DIR (run scripts/evaluate_baseline.sh)"
fi

echo "== Cutover contract tests =="
uv run pytest tests/contracts/test_go_live_cutover_v3_contract.py -q --tb=short

if [[ "${STRICT}" == "1" ]]; then
  echo "== Pilot soak dry-run =="
  bash scripts/load/run_pilot_soak.sh
fi

echo "Go-live preflight v3 passed (sha=${GIT_SHA})."
