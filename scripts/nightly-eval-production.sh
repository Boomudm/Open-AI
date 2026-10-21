#!/usr/bin/env bash
# Production-path nightly evaluation — real embeddings + LLM (factory cron mirror).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILE="${EVAL_PROFILE:-production}"
REPORT="${REPORT_PATH:-docs/eval-report-production-nightly.json}"
LOCK="${BASELINE_LOCK:-configs/evaluation_baseline_lock_production.json}"
THRESHOLD="${EVAL_PASS_THRESHOLD:-90.91}"
MAX_REGRESSION="${MAX_REGRESSION_PCT:-3}"

unset SPARK_SEED_SKIP_EMBED

echo "Production nightly eval (profile=${PROFILE}, lock=${LOCK})"

uv run python scripts/evaluate_baseline.py \
  --suite baseline \
  --json-output "$REPORT" \
  --baseline-lock "$LOCK" \
  --max-regression-pct "$MAX_REGRESSION"

uv run python scripts/validate_baseline_lock.py \
  --lock "$LOCK" \
  --report "$REPORT" \
  --min-pass-pct "$THRESHOLD"

pass_pct="$(python3 - <<PY
import json
from pathlib import Path
data = json.loads(Path("${REPORT}").read_text(encoding="utf-8"))
print(data.get("metrics", {}).get("overall_case_pass_pct", 0))
PY
)"

echo "Production nightly pass rate: ${pass_pct}% (threshold ${THRESHOLD}%)"

if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  curl -sS -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"Neo Chat production nightly eval: ${pass_pct}% pass (threshold ${THRESHOLD}%)\"}" \
    "$SLACK_WEBHOOK_URL" >/dev/null || true
fi
