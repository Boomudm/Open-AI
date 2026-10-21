#!/usr/bin/env bash
# Dry-run checks for release_gate.sh and production lock v3 (Phase 13).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

test -x scripts/release_gate.sh || test -f scripts/release_gate.sh
test -f scripts/evaluate_baseline.sh
test -f configs/eval/production_lock_v3.json
test -f configs/production_lock_v3.yaml

uv run python scripts/validate_production_lock_v3.py --lock configs/eval/production_lock_v3.json
uv run python scripts/remediation_v3_phase_gate.py --phase 13 --skip-contracts

echo "release_gate dry-run checks passed"
