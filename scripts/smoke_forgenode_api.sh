#!/usr/bin/env bash
# Smoke test ForgeNode public API endpoints.
#
# Usage:
#   scripts/smoke_forgenode_api.sh
#   BASE_URL=https://forge.kcalsion.com scripts/smoke_forgenode_api.sh
#   CHAT_TOKEN=... V1_TOKEN=... scripts/smoke_forgenode_api.sh
set -u

BASE_URL="${BASE_URL:-https://forge.kcalsion.com}"
CHAT_TOKEN="${CHAT_TOKEN:-ck-openrte-web-2026}"
V1_TOKEN="${V1_TOKEN:-dev4_lenovo_server_api_key}"

# If the URL is provided without a scheme, default to https.
if [[ "$BASE_URL" != http://* && "$BASE_URL" != https://* ]]; then
  BASE_URL="https://${BASE_URL}"
fi
BASE_URL="${BASE_URL%/}"

CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-5}"
DEFAULT_TIMEOUT="${DEFAULT_TIMEOUT:-20}"
CHAT_TIMEOUT="${CHAT_TIMEOUT:-35}"
RERANK_TIMEOUT="${RERANK_TIMEOUT:-25}"

PASS_COUNT=0
FAIL_COUNT=0

declare -a PASS_ITEMS=()
declare -a FAIL_ITEMS=()

print_header() {
  echo "ForgeNode smoke test"
  echo "base_url: $BASE_URL"
  echo
}

record_pass() {
  local label="$1"
  PASS_COUNT=$((PASS_COUNT + 1))
  PASS_ITEMS+=("$label")
  echo "PASS - $label"
}

record_fail() {
  local label="$1"
  local reason="$2"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAIL_ITEMS+=("$label :: $reason")
  echo "FAIL - $label :: $reason"
}

request_json() {
  local method="$1"
  local path="$2"
  local timeout="$3"
  local token="$4"
  local payload="${5:-}"
  local output=""
  local curl_rc=0
  local url="${BASE_URL}${path}"

  if [[ "$method" == "GET" ]]; then
    set +e
    output="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" -m "$timeout" \
      -H "Authorization: Bearer $token" \
      -w $'\n__HTTP_STATUS__:%{http_code}' \
      "$url" 2>&1)"
    curl_rc=$?
    set -e
  else
    set +e
    output="$(curl -sS --connect-timeout "$CONNECT_TIMEOUT" -m "$timeout" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "$payload" \
      -w $'\n__HTTP_STATUS__:%{http_code}' \
      "$url" 2>&1)"
    curl_rc=$?
    set -e
  fi

  local status
  status="$(printf '%s\n' "$output" | rg '^__HTTP_STATUS__:' -r '$0' | awk -F: '{print $2}' | tr -d '[:space:]')"
  local body
  body="$(printf '%s\n' "$output" | rg -v '^__HTTP_STATUS__:')"

  printf '%s\n%s\n%s\n' "$curl_rc" "${status:-000}" "$body"
}

json_has_key() {
  local body="$1"
  local key="$2"
  python3 - "$key" "$body" <<'PY'
import json
import sys

key = sys.argv[1]
try:
    data = json.loads(sys.argv[2])
except Exception:
    print("invalid-json")
    sys.exit(2)

if key in data:
    sys.exit(0)
sys.exit(1)
PY
}

short_body() {
  local body="$1"
  if [[ ${#body} -gt 240 ]]; then
    printf '%s...' "${body:0:240}"
  else
    printf '%s' "$body"
  fi
}

check_health() {
  local result
  result="$(request_json "GET" "/health" "$DEFAULT_TIMEOUT" "$CHAT_TOKEN")"
  local rc status body
  rc="$(printf '%s\n' "$result" | sed -n '1p')"
  status="$(printf '%s\n' "$result" | sed -n '2p')"
  body="$(printf '%s\n' "$result" | sed -n '3,$p')"

  if [[ "$rc" == "0" && "$status" == "200" ]] && json_has_key "$body" "status"; then
    record_pass "GET /health"
  else
    record_fail "GET /health" "curl_rc=$rc http=$status body=$(short_body "$body")"
  fi
}

check_models() {
  local result
  result="$(request_json "GET" "/v1/models" "$DEFAULT_TIMEOUT" "$CHAT_TOKEN")"
  local rc status body
  rc="$(printf '%s\n' "$result" | sed -n '1p')"
  status="$(printf '%s\n' "$result" | sed -n '2p')"
  body="$(printf '%s\n' "$result" | sed -n '3,$p')"

  if [[ "$rc" == "0" && "$status" == "200" ]] && json_has_key "$body" "data"; then
    record_pass "GET /v1/models"
  else
    record_fail "GET /v1/models" "curl_rc=$rc http=$status body=$(short_body "$body")"
  fi
}

check_chat() {
  local payload='{"model":"qwen3.6:35b-a3b","messages":[{"role":"user","content":"ตอบสั้นๆ ว่าคุณคือโมเดลอะไร"}],"max_tokens":100}'
  local attempts=2
  local attempt=1
  while [[ $attempt -le $attempts ]]; do
    local result rc status body
    result="$(request_json "POST" "/v1/chat/completions" "$CHAT_TIMEOUT" "$CHAT_TOKEN" "$payload")"
    rc="$(printf '%s\n' "$result" | sed -n '1p')"
    status="$(printf '%s\n' "$result" | sed -n '2p')"
    body="$(printf '%s\n' "$result" | sed -n '3,$p')"

    if [[ "$rc" == "0" && "$status" == "200" ]] && json_has_key "$body" "choices"; then
      if [[ $attempt -gt 1 ]]; then
        record_pass "POST /v1/chat/completions (attempt $attempt/$attempts)"
      else
        record_pass "POST /v1/chat/completions"
      fi
      return
    fi
    attempt=$((attempt + 1))
  done
  record_fail "POST /v1/chat/completions" "timeout/error after ${attempts} attempts"
}

check_embeddings() {
  local payload='{"model":"bge-m3","input":"ทดสอบภาษาไทย"}'
  local result rc status body
  result="$(request_json "POST" "/v1/embeddings" "$DEFAULT_TIMEOUT" "$V1_TOKEN" "$payload")"
  rc="$(printf '%s\n' "$result" | sed -n '1p')"
  status="$(printf '%s\n' "$result" | sed -n '2p')"
  body="$(printf '%s\n' "$result" | sed -n '3,$p')"

  if [[ "$rc" == "0" && "$status" == "200" ]] && json_has_key "$body" "data"; then
    record_pass "POST /v1/embeddings"
  else
    record_fail "POST /v1/embeddings" "curl_rc=$rc http=$status body=$(short_body "$body")"
  fi
}

check_rerank() {
  local payload='{"model":"Qwen/Qwen3-Reranker-0.6B","query":"อาหารไทย","documents":["ต้มยำกุ้งเป็นอาหารไทย","วิธีซ่อมเครื่องยนต์","แกงเขียวหวานใช้กะทิ"],"top_n":2,"return_documents":true}'
  local attempts=2
  local attempt=1
  while [[ $attempt -le $attempts ]]; do
    local result rc status body
    result="$(request_json "POST" "/v1/rerank" "$RERANK_TIMEOUT" "$V1_TOKEN" "$payload")"
    rc="$(printf '%s\n' "$result" | sed -n '1p')"
    status="$(printf '%s\n' "$result" | sed -n '2p')"
    body="$(printf '%s\n' "$result" | sed -n '3,$p')"

    if [[ "$rc" == "0" && "$status" == "200" ]] && (json_has_key "$body" "results" || json_has_key "$body" "data"); then
      if [[ $attempt -gt 1 ]]; then
        record_pass "POST /v1/rerank (attempt $attempt/$attempts)"
      else
        record_pass "POST /v1/rerank"
      fi
      return
    fi
    attempt=$((attempt + 1))
  done
  record_fail "POST /v1/rerank" "timeout/error after ${attempts} attempts"
}

print_summary() {
  echo
  echo "Summary"
  echo "-------"
  echo "pass: $PASS_COUNT"
  echo "fail: $FAIL_COUNT"

  if [[ ${#PASS_ITEMS[@]} -gt 0 ]]; then
    echo
    echo "Passed checks:"
    printf ' - %s\n' "${PASS_ITEMS[@]}"
  fi

  if [[ ${#FAIL_ITEMS[@]} -gt 0 ]]; then
    echo
    echo "Failed checks:"
    printf ' - %s\n' "${FAIL_ITEMS[@]}"
  fi
}

main() {
  set -e
  print_header
  check_health
  check_models
  check_chat
  check_embeddings
  check_rerank
  print_summary

  if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
