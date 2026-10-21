#!/usr/bin/env bash
# Optional POC — AnythingLLM (not wired to Neo Chat production UC4/UC5).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/anything-llm/docker"
docker compose up -d
echo "[anything-llm] UI typically http://localhost:3001"
echo "Compare RAG answers with Neo Chat web; export docs to data/inbox/ for Neo Chat ingest."
