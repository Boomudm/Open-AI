#!/usr/bin/env bash
# App-layer legacy pattern ban (remediation_blueprint_app_layer Phase 13).
# Fails if forbidden patterns reappear outside explicit allowlists.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

failures=0

is_test_path() {
  local rel="$1"
  [[ "$rel" =~ ^tests/ ]]
}

report_hit() {
  echo "  BANNED: $1"
  failures=$((failures + 1))
}

# --- access_token= query JWT (SSE auth) --------------------------------------
# Allow: OAuth token exchange, contract tests asserting rejection.
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if is_test_path "$rel"; then
    continue
  fi
  if [[ "$rel" == "src/spark/core/google_oauth.py" ]]; then
    continue
  fi
  if rg -q 'access_token=' "$file" 2>/dev/null; then
    report_hit "$rel matches access_token= (query JWT transport)"
  fi
done < <(rg -l 'access_token=' --glob '*.py' --glob '*.ts' --glob '*.tsx' . 2>/dev/null || true)

while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if is_test_path "$rel"; then
    continue
  fi
  if rg -q 'query_params\.get\(["'\'']access_token["'\'']\)' "$file" 2>/dev/null; then
    report_hit "$rel reads access_token query param"
  fi
done < <(rg -l 'query_params\.get\(["'\'']access_token["'\'']\)' src web 2>/dev/null || true)

# --- localStorage JWT --------------------------------------------------------
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if rg -q 'localStorage\.getItem\(["'\'']spark_token["'\'']\)' "$file" 2>/dev/null; then
    report_hit "$rel uses localStorage spark_token"
  fi
done < <(rg -l 'localStorage\.getItem\(["'\'']spark_token["'\'']\)' web 2>/dev/null || true)

# --- In-process export counter (Phase 1) -------------------------------------
if rg -q '_EXPORT_COUNTER' src web 2>/dev/null; then
  while IFS= read -r file; do
    report_hit "${file#"$ROOT/"} references _EXPORT_COUNTER"
  done < <(rg -l '_EXPORT_COUNTER' src web 2>/dev/null || true)
fi

# --- Alerts DB poll loop (Phase 3) -------------------------------------------
if rg -q 'POLL_INTERVAL_SEC = 4' src 2>/dev/null; then
  while IFS= read -r file; do
    report_hit "${file#"$ROOT/"} has POLL_INTERVAL_SEC = 4 (alerts poll loop)"
  done < <(rg -l 'POLL_INTERVAL_SEC = 4' src 2>/dev/null || true)
fi

# --- SYSTEM_PRINCIPAL outside security module + tests ------------------------
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if [[ "$rel" == "src/spark/core/security.py" ]]; then
    continue
  fi
  if is_test_path "$rel"; then
    continue
  fi
  if rg -q 'SYSTEM_PRINCIPAL' "$file" 2>/dev/null; then
    report_hit "$rel references SYSTEM_PRINCIPAL outside security.py"
  fi
done < <(rg -l 'SYSTEM_PRINCIPAL' --glob '*.py' src tests 2>/dev/null || true)

# --- Production default: live tokens off -------------------------------------
if rg -q 'spark_stream_live_tokens:\s*bool\s*=\s*False' src/spark/core/config.py 2>/dev/null; then
  report_hit "config.py defaults spark_stream_live_tokens=False"
fi

# --- Deprecated frontend shims -------------------------------------------------
if [[ -f web/lib/chatStream.ts ]]; then
  report_hit "web/lib/chatStream.ts deprecated shim still present"
fi

if [[ -f web/components/ui/VirtualList.tsx ]]; then
  report_hit "web/components/ui/VirtualList.tsx dead component still present"
fi

# --- ingest_scope position writes must route through mutation hooks (v2 Phase 4) ---
if rg -q 'async def set_document_job_positions' src/spark/services/ingest_scope.py 2>/dev/null; then
  if ! rg -q 'on_document_positions_changed' src/spark/services/ingest_scope.py 2>/dev/null; then
    report_hit "ingest_scope.set_document_job_positions missing mutation_hooks call"
  fi
fi

# --- v2 advisory scan (strict via banned_patterns_v2.sh + phase gate) -----------
if [[ -f scripts/app_layer/banned_patterns_v2.sh ]]; then
  APP_LAYER_V2_BANNED_STRICT=1 bash scripts/app_layer/banned_patterns_v2.sh
fi

if [[ "$failures" -gt 0 ]]; then
  echo ""
  echo "banned_patterns.sh FAILED ($failures hit(s))"
  exit 1
fi

echo "banned_patterns.sh passed."
