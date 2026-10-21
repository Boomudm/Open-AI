#!/usr/bin/env bash
# Pre-release gate — contracts, eval suites, production lock v3 (Phase 13).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILE="${1:-production}"
if [[ "${1:-}" == "--profile" ]]; then
  PROFILE="${2:-production}"
fi

GIT_SHA="${GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo local)}"
REPORT_DIR="${REPORT_DIR:-reports/eval/${GIT_SHA}}"
LOCK="${LOCK:-configs/eval/production_lock_v3.json}"

LIVE_API_FLAGS=()
if [[ "${PROFILE}" != "production" ]]; then
  LIVE_API_FLAGS+=(--skip-requires-live-api)
fi

echo "Neo Chat release gate (profile=${PROFILE})"

echo "== Remediation v3 phase 13 gate =="
uv run python scripts/remediation_v3_phase_gate.py --phase 13 --skip-contracts

echo "== Contract tests =="
uv run pytest tests/contracts/ -q --tb=short

echo "== Ingest config validation =="
uv run python scripts/validate_ingest_configs.py

echo "== Production lock v3 structure =="
uv run python scripts/validate_production_lock_v3.py --lock "$LOCK"

echo "== Leakage audit (dev vs held-out) =="
uv run python scripts/eval_leakage_audit.py \
  --dev configs/evaluation_baseline.yaml \
  --holdout configs/evaluation_heldout.yaml

mkdir -p "$REPORT_DIR"

echo "== baseline_ci =="
uv run python scripts/evaluate_baseline.py \
  --config configs/eval/baseline_ci.yaml \
  --deterministic-rag \
  "${LIVE_API_FLAGS[@]}" \
  --json-output "$REPORT_DIR/baseline_ci.json"

echo "== adversarial =="
uv run python scripts/evaluate_baseline.py \
  --suite adversarial \
  --deterministic-rag \
  "${LIVE_API_FLAGS[@]}" \
  --require-answer-path \
  --json-output "$REPORT_DIR/adversarial.json"

echo "== safety_critical =="
uv run python scripts/evaluate_baseline.py \
  --suite safety_critical \
  --deterministic-rag \
  "${LIVE_API_FLAGS[@]}" \
  --require-answer-path \
  --json-output "$REPORT_DIR/safety_critical.json"

echo "== grounding =="
uv run python scripts/evaluate_baseline.py \
  --suite grounding \
  --deterministic-rag \
  "${LIVE_API_FLAGS[@]}" \
  --json-output "$REPORT_DIR/grounding.json"

echo "== heldout =="
uv run python scripts/evaluate_baseline.py \
  --suite heldout \
  --deterministic-rag \
  "${LIVE_API_FLAGS[@]}" \
  --require-answer-path \
  --json-output "$REPORT_DIR/heldout.json"

echo "== Outcome gate (strict) =="
uv run python scripts/validate_production_lock_v3.py \
  --lock "$LOCK" \
  --report-dir "$REPORT_DIR" \
  --strict

echo "Release gate passed (profile=${PROFILE}, reports=${REPORT_DIR})."
