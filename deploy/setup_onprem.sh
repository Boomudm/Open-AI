#!/usr/bin/env bash
# Neo Chat — one-click on-premise factory deployment
#
# Usage:
#   chmod +x deploy/setup_onprem.sh
#   ./deploy/setup_onprem.sh              # full install
#   ./deploy/setup_onprem.sh --seed         # also load demo users/machines
#   ./deploy/setup_onprem.sh --pull-models  # pull Ollama LLM model
#   ./deploy/setup_onprem.sh --with-mcp     # enable predictive MCP profile
#   ./deploy/setup_onprem.sh --validate     # health check only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT/deploy"
ENV_FILE="$DEPLOY_DIR/.env"
ENV_EXAMPLE="$DEPLOY_DIR/.env.onprem.example"

COMPOSE=(docker compose -f "$DEPLOY_DIR/docker-compose.onprem.yml" --env-file "$ENV_FILE" --project-directory "$DEPLOY_DIR")

SEED=false
PULL_MODELS=false
WITH_MCP=false
VALIDATE_ONLY=false
SKIP_BUILD=false

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "$0"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED=true; shift ;;
    --pull-models) PULL_MODELS=true; shift ;;
    --with-mcp) WITH_MCP=true; shift ;;
    --validate) VALIDATE_ONLY=true; shift ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    -h|--help) usage ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

check_prerequisites() {
  require_cmd docker
  docker compose version >/dev/null 2>&1 || die "docker compose v2 required"
  if ! docker info >/dev/null 2>&1; then
    die "Docker daemon not running — start Docker and retry"
  fi
  local mem_kb
  mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  if [[ "$mem_kb" -gt 0 && "$mem_kb" -lt 12000000 ]]; then
    echo "WARN: less than 12 GB RAM detected — use LLM_PROFILE=demo and lower concurrency"
  fi
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "Creating $ENV_FILE from template..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  fi
  if grep -q 'CHANGE_ME' "$ENV_FILE"; then
    log "Generating secrets for CHANGE_ME placeholders..."
    local jwt pg minio ro
    jwt="$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')"
    pg="$(openssl rand -hex 16 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(16))')"
    minio="$(openssl rand -hex 16 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(16))')"
    ro="$(openssl rand -hex 16 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(16))')"
    # shellcheck disable=SC2016
    sed -i.bak \
      -e "s/JWT_SECRET=CHANGE_ME_generate_with_openssl_rand_hex_32/JWT_SECRET=${jwt}/" \
      -e "s/POSTGRES_PASSWORD=CHANGE_ME_strong_postgres_password/POSTGRES_PASSWORD=${pg}/" \
      -e "s/POSTGRES_SQL_READONLY_PASSWORD=CHANGE_ME_sql_readonly_password/POSTGRES_SQL_READONLY_PASSWORD=${ro}/" \
      -e "s/MINIO_ROOT_PASSWORD=CHANGE_ME_minio_password/MINIO_ROOT_PASSWORD=${minio}/" \
      "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
    log "Secrets generated — review $ENV_FILE and set ONPREM_PUBLIC_URL to your LAN hostname"
  fi
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
}

ensure_data_dirs() {
  local base="${SPARK_DATA_DIR:-./data}"
  log "Creating data directories under $DEPLOY_DIR/$base ..."
  mkdir -p "$DEPLOY_DIR/$base"/{inbox,raw,documents,machines,feedback,chat_attachments,agentic}
}

compose_up() {
  local -a profiles=()
  if [[ "$WITH_MCP" == true ]]; then
    profiles+=(--profile mcp)
    log "Enabling predictive MCP sidecar (build image separately if missing)"
  fi
  if [[ "$SKIP_BUILD" == false ]]; then
    log "Building images (first run may take 15–30 minutes)..."
    "${COMPOSE[@]}" "${profiles[@]}" build
  fi
  log "Starting infrastructure + migrations + application..."
  "${COMPOSE[@]}" "${profiles[@]}" up -d
}

wait_healthy() {
  log "Waiting for API health..."
  local url="http://127.0.0.1:${ONPREM_HTTP_PORT:-80}/healthz"
  for _ in $(seq 1 60); do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "    API reachable via nginx at $url"
      return 0
    fi
    sleep 3
  done
  die "API not healthy after 3 minutes — run: ${COMPOSE[*]} logs api nginx"
}

pull_ollama_models() {
  local model="${OLLAMA_LLM_MODEL:-qwen2.5:7b-instruct}"
  log "Pulling Ollama model: $model (may take several minutes)..."
  "${COMPOSE[@]}" exec -T ollama ollama pull "$model" || die "Ollama pull failed"
}

run_seed() {
  log "Seeding demo factory data (admin / changeme)..."
  "${COMPOSE[@]}" exec -T api python scripts/seed_demo.py --skip-maintenance
  log "Ensuring Qdrant payload indexes..."
  "${COMPOSE[@]}" exec -T api python scripts/ensure_qdrant_indexes.py || true
}

validate_stack() {
  log "Readiness check..."
  curl -sf "http://127.0.0.1:${ONPREM_HTTP_PORT:-80}/healthz" | head -c 200
  echo
  curl -sf "http://127.0.0.1:${ONPREM_HTTP_PORT:-80}/api/v1/rag/health" 2>/dev/null | head -c 200 || true
  echo
  "${COMPOSE[@]}" ps
}

print_summary() {
  local pub="${ONPREM_PUBLIC_URL:-http://spark.lan}"
  cat <<EOF

╔══════════════════════════════════════════════════════════════════╗
║  Neo Chat on-premise deployment complete                         ║
╠══════════════════════════════════════════════════════════════════╣
║  Web UI:     ${pub}
║  API docs:   ${pub}/docs
║  Health:     ${pub}/healthz
╠══════════════════════════════════════════════════════════════════╣
║  IT checklist:
║    1. Add DNS: spark.lan → this server LAN IP
║    2. Open firewall port ${ONPREM_HTTP_PORT:-80} for factory subnet only
║    3. Change default admin password after first login
║    4. Back up deploy/data/ and Docker volumes regularly
╠══════════════════════════════════════════════════════════════════╣
║  Commands:
║    Logs:   ${COMPOSE[*]} logs -f api celery_worker
║    Stop:   ${COMPOSE[*]} down
║    Update: git pull && ./deploy/setup_onprem.sh --skip-build
╚══════════════════════════════════════════════════════════════════╝
EOF
  if [[ "$SEED" == true ]]; then
    echo "  Demo login: admin / changeme  (change immediately in production)"
  fi
}

main() {
  cd "$ROOT"
  check_prerequisites
  ensure_env
  if [[ "$VALIDATE_ONLY" == true ]]; then
    validate_stack
    exit 0
  fi
  ensure_data_dirs
  compose_up
  if [[ "$PULL_MODELS" == true ]]; then
    pull_ollama_models
  fi
  wait_healthy
  if [[ "$SEED" == true ]]; then
    run_seed
  fi
  validate_stack
  print_summary
}

main "$@"
