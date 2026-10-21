#!/usr/bin/env bash
# CI quality gate: runs RAG evaluation suite and blocks merge on regressions.
#
# Usage:
#   ./scripts/ci_eval_gate.sh [suite_name]
#
# Requires: running PostgreSQL, Qdrant, Redis, and seeded demo data.
# Produces: reports/ci_eval_report.json with full metrics.

set -euo pipefail

SUITE="${1:-golden_real_docs}"
REPORT_DIR="reports"
REPORT_FILE="${REPORT_DIR}/ci_eval_report.json"

mkdir -p "$REPORT_DIR"

echo "╔══════════════════════════════════════════════╗"
echo "║  RAG CI Evaluation Gate — suite: ${SUITE}    ║"
echo "╚══════════════════════════════════════════════╝"

export SPARK_PROFILE="${SPARK_PROFILE:-test}"
export SPARK_SEED_SKIP_EMBED="${SPARK_SEED_SKIP_EMBED:-1}"

python -m spark.eval.ci_eval_runner \
    --suite "$SUITE" \
    --threshold-file configs/eval/thresholds.yaml \
    --output-json "$REPORT_FILE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✓ RAG evaluation gate PASSED"
else
    echo ""
    echo "✗ RAG evaluation gate FAILED — see report: ${REPORT_FILE}"
fi

exit $EXIT_CODE
