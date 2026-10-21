#!/usr/bin/env bash
# Production Next.js standalone — load server secrets before starting server.js.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STANDALONE="$ROOT/web/.next/standalone"

# Next standalone output does not include static/public assets automatically.
# Keep the runtime directory complete so /_next/static/* CSS/JS and public files
# are served after rebuilds and reboots.
mkdir -p "$STANDALONE/.next"
rm -rf "$STANDALONE/.next/static"
cp -a "$ROOT/web/.next/static" "$STANDALONE/.next/static"
rm -rf "$STANDALONE/public"
cp -a "$ROOT/web/public" "$STANDALONE/public"

if [[ -f "$ROOT/web/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/web/.env.local"
  set +a
elif [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

NODE_BIN="${NODE_BIN:-}"
if [[ -z "$NODE_BIN" ]]; then
  for candidate in \
    /home/jetson/.nvm/versions/node/v20.20.2/bin/node \
    "$HOME/.nvm/versions/node/"*/bin/node \
    "$(command -v node 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      NODE_BIN="$candidate"
      break
    fi
  done
fi
if [[ -z "$NODE_BIN" || ! -x "$NODE_BIN" ]]; then
  echo "node not found — set NODE_BIN or install Node via nvm" >&2
  exit 127
fi

cd "$STANDALONE"
exec "$NODE_BIN" server.js
