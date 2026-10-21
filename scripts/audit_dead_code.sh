#!/usr/bin/env bash
# Dead-code and legacy-config audit (Phase 13).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Config documentation surface =="
uv run python scripts/validate_config_docs.py

echo "== Optional vulture pass (confidence >= 80) =="
if uv run vulture src/spark --min-confidence 80 2>/dev/null; then
  echo "vulture: no high-confidence dead code"
else
  echo "vulture: findings reported (non-blocking unless CI strict mode enabled)"
fi

echo "== Legacy RAGFlow references in src/ =="
ALLOWLIST=(
  "src/spark/core/deprecated_config.py"
)
hits=0
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  skip=0
  for allowed in "${ALLOWLIST[@]}"; do
    if [[ "$rel" == "$allowed" ]]; then
      skip=1
      break
    fi
  done
  if [[ "$skip" -eq 1 ]]; then
    continue
  fi
  echo "  forbidden ragflow reference: ${rel}"
  hits=$((hits + 1))
done < <(rg -l -i 'ragflow' src/ || true)

if [[ "$hits" -gt 0 ]]; then
  echo "FAIL: remove RAGFlow references from src/ (allowed: deprecated_config env audit)"
  exit 1
fi

echo "audit_dead_code.sh passed."
