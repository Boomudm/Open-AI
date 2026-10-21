#!/usr/bin/env bash
# Build the Next.js frontend for production (standalone output) and stage the
# static/public assets standalone mode needs but does not copy itself.
#
# Why this script exists: `output: standalone` in next.config.mjs produces a
# self-contained server.js + traced node_modules, but Next.js deliberately
# does NOT copy .next/static or public/ into it — those must be copied by the
# deploy step or every asset 404s / next/image optimization fails ("'sharp'
# is required..." if sharp itself is also missing from the trace).
#
# Usage: scripts/build_web.sh   (then: sudo systemctl restart spark-web)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/web"

npm run build

mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static .next/standalone/public
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public

# Standalone server verifies JWT cookies at runtime (middleware + /api/auth/session).
# Without this file it falls back to dev-secret-change-me while the API uses .env JWT_SECRET.
if [[ -f .env.local ]]; then
  grep -E '^(JWT_SECRET=)' .env.local > .next/standalone/.env.production.local
elif [[ -f ../.env ]]; then
  grep -E '^(JWT_SECRET=)' ../.env > .next/standalone/.env.production.local
fi

echo "==> Standalone build ready at web/.next/standalone/server.js"
echo "==> Restart the service: sudo systemctl restart spark-web"
