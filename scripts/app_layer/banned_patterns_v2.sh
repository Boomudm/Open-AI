#!/usr/bin/env bash
# App-layer v2 legacy pattern ban (remediation_blueprint_app_layerv2).
# Strict enforcement from Phase 12; run in advisory mode until then:
#   APP_LAYER_V2_BANNED_STRICT=0  → warn only (default before Phase 12)
#   APP_LAYER_V2_BANNED_STRICT=1  → fail CI
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

STRICT="${APP_LAYER_V2_BANNED_STRICT:-0}"
failures=0
warnings=0

is_test_path() {
  local rel="$1"
  [[ "$rel" =~ ^tests/ ]] || [[ "$rel" =~ __tests__ ]]
}

report_hit() {
  local msg="$1"
  if [[ "$STRICT" == "1" ]]; then
    echo "  BANNED: $msg"
    failures=$((failures + 1))
  else
    echo "  WARN (v2): $msg"
    warnings=$((warnings + 1))
  fi
}

# --- Non-atomic pop_json on security-sensitive paths (Phase 2) ----------------
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if is_test_path "$rel"; then
    continue
  fi
  if [[ "$rel" == "src/spark/core/cache.py" ]]; then
    continue
  fi
  if rg -q '\.pop_json\(' "$file" 2>/dev/null; then
    report_hit "$rel uses pop_json (use atomic_pop_json for tickets/secrets)"
  fi
done < <(rg -l '\.pop_json\(' src/spark/services/streams src/spark/core/oauth_exchange.py 2>/dev/null || true)

# --- Raw fetch in chat lib (Phase 6) ------------------------------------------
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if is_test_path "$rel"; then
    continue
  fi
  if rg -q '\bfetch\(' "$file" 2>/dev/null; then
    report_hit "$rel uses raw fetch (route SSE through lib/streams/fabric.ts)"
  fi
done < <(rg -l '\bfetch\(' web/lib/chat --glob '*.ts' 2>/dev/null || true)

# --- Dead askStream shim (Phase 6) --------------------------------------------
if rg -q 'export async function askStream' web/lib/api/chat.ts 2>/dev/null; then
  report_hit "web/lib/api/chat.ts still exports askStream"
fi

# --- Deleted frontend stream shims (Phase 6 / 13) -----------------------------
if [[ -f web/lib/chat/stream-consumer.ts ]]; then
  report_hit "web/lib/chat/stream-consumer.ts must be deleted (use lib/streams/fabric.ts)"
fi

if [[ -f src/spark/api/platform/sliding_window.py ]]; then
  report_hit "src/spark/api/platform/sliding_window.py shim still present (use rate_limit_lua.py)"
fi

# --- Alert ACL null factory allow (Phase 3/4) -----------------------------------
if rg -q 'factory_id is None' src/spark/services/streams/alert_stream_service.py 2>/dev/null; then
  if rg -q 'return True' src/spark/services/streams/alert_stream_service.py 2>/dev/null; then
    if rg -q 'if factory_id is None:\s*\n\s*return True' src/spark/services/streams/alert_stream_service.py 2>/dev/null \
      || rg -A1 'factory_id is None' src/spark/services/streams/alert_stream_service.py 2>/dev/null | rg -q 'return True'; then
      report_hit "alert_stream_service allows null factory_id for non-admin"
    fi
  fi
fi

# --- Direct bump_factory_acl from endpoints (Phase 4) ---------------------------
while IFS= read -r file; do
  rel="${file#"$ROOT/"}"
  rel="${rel#./}"
  if [[ "$rel" == src/spark/services/acl/cache_invalidation.py ]]; then
    continue
  fi
  if [[ "$rel" == src/spark/services/acl/mutation_hooks.py ]]; then
    continue
  fi
  if is_test_path "$rel"; then
    continue
  fi
  if rg -q 'bump_factory_acl_version' "$file" 2>/dev/null; then
    report_hit "$rel calls bump_factory_acl_version outside mutation_hooks"
  fi
done < <(rg -l 'bump_factory_acl_version' src/spark/api 2>/dev/null || true)

# --- Stream ticket without freshness check in auth middleware (Phase 2) ---------
if rg -q 'principal_from_stream_ticket\(ticket_claims\)' src/spark/core/security.py 2>/dev/null; then
  report_hit "auth_middleware uses principal_from_stream_ticket without freshness check"
fi

if [[ "$failures" -gt 0 ]]; then
  echo ""
  echo "banned_patterns_v2.sh FAILED ($failures hit(s), strict=$STRICT)"
  exit 1
fi

if [[ "$warnings" -gt 0 ]]; then
  echo "banned_patterns_v2.sh passed with $warnings advisory warning(s) (strict=$STRICT)"
else
  echo "banned_patterns_v2.sh passed."
fi
