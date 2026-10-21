#!/usr/bin/env bash
# Nightly full-LLM evaluation on factory host (cron 02:00).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPORT="${REPORT_PATH:-docs/eval-report-nightly.json}"
THRESHOLD="${EVAL_PASS_THRESHOLD:-75}"

uv run python scripts/evaluate_baseline.py --json-output "$REPORT"

pass_pct="$(REPORT_PATH="$REPORT" python3 - <<'PY'
import json
import os

with open(os.environ["REPORT_PATH"], encoding="utf-8") as f:
    data = json.load(f)
print(data.get("summary", {}).get("pass_pct", 0))
PY
)"

echo "Nightly eval pass rate: ${pass_pct}% (threshold ${THRESHOLD}%)"
python3 - <<PY
pct = float("${pass_pct}")
threshold = float("${THRESHOLD}")
raise SystemExit(0 if pct >= threshold else 1)
PY

if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  curl -sS -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"Neo Chat nightly eval: ${pass_pct}% pass (threshold ${THRESHOLD}%)\"}" \
    "$SLACK_WEBHOOK_URL" >/dev/null || true
fi
