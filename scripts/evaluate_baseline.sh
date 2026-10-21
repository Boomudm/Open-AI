#!/usr/bin/env bash
# Run all production_lock_v3 suites and validate report outcomes (Phase 13).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GIT_SHA="${GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo local)}"
REPORT_DIR="${REPORT_DIR:-reports/eval/${GIT_SHA}}"
LOCK="${LOCK:-configs/eval/production_lock_v3.json}"

mkdir -p "$REPORT_DIR"

echo "== Validate production lock v3 structure =="
uv run python scripts/validate_production_lock_v3.py --lock "$LOCK"

echo "== baseline_ci =="
uv run python scripts/evaluate_baseline.py \
  --config configs/eval/baseline_ci.yaml \
  --deterministic-rag \
  --skip-requires-live-api \
  --json-output "$REPORT_DIR/baseline_ci.json"

echo "== adversarial =="
uv run python scripts/evaluate_baseline.py \
  --suite adversarial \
  --deterministic-rag \
  --skip-requires-live-api \
  --require-answer-path \
  --json-output "$REPORT_DIR/adversarial.json"

echo "== safety_critical =="
uv run python scripts/evaluate_baseline.py \
  --suite safety_critical \
  --deterministic-rag \
  --skip-requires-live-api \
  --require-answer-path \
  --json-output "$REPORT_DIR/safety_critical.json"

echo "== grounding =="
uv run python scripts/evaluate_baseline.py \
  --suite grounding \
  --deterministic-rag \
  --skip-requires-live-api \
  --json-output "$REPORT_DIR/grounding.json"

echo "== heldout =="
uv run python scripts/evaluate_baseline.py \
  --suite heldout \
  --deterministic-rag \
  --skip-requires-live-api \
  --require-answer-path \
  --json-output "$REPORT_DIR/heldout.json"

echo "== Outcome gate (strict) =="
uv run python scripts/validate_production_lock_v3.py \
  --lock "$LOCK" \
  --report-dir "$REPORT_DIR" \
  --strict

echo "evaluate_baseline.sh passed (reports=$REPORT_DIR lock=$LOCK)"
