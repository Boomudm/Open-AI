#!/usr/bin/env bash
# Route Python/ML caches and temp files to repo-local storage on NVMe.
# eMMC /tmp (~2 GB free) fills quickly when uv/pip/HF download large wheels.
#
# Usage (from repo root):
#   source scripts/env_nvme_cache.sh
#   uv sync --extra dev
#   uv run pytest tests/ -q
#
# Wired into scripts/dev.sh and scripts/jetson/bootstrap_compute.sh.

if [[ -n "${SPARK_NVME_CACHE_LOADED:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_CACHE="$_ROOT/.cache"

# Always prefer repo-local NVMe paths. Cursor/sandbox may pre-set UV_CACHE_DIR
# under eMMC /tmp (low disk); overriding avoids "No space left on device".
export UV_CACHE_DIR="$_CACHE/uv"
export TMPDIR="$_CACHE/tmp"
export HF_HOME="$_CACHE/huggingface"
export TRANSFORMERS_CACHE="$_CACHE/huggingface"
export HUGGINGFACE_HUB_CACHE="$_CACHE/huggingface/hub"
export PIP_CACHE_DIR="$_CACHE/pip"
export XDG_CACHE_HOME="$_CACHE/xdg"
export RUFF_CACHE_DIR="$_CACHE/ruff"
export NPM_CONFIG_CACHE="$_CACHE/npm"

mkdir -p \
  "$UV_CACHE_DIR" \
  "$TMPDIR" \
  "$HF_HOME" \
  "$HUGGINGFACE_HUB_CACHE" \
  "$PIP_CACHE_DIR" \
  "$XDG_CACHE_HOME" \
  "$RUFF_CACHE_DIR" \
  "$NPM_CONFIG_CACHE" \
  "$_CACHE/ingest"

SPARK_NVME_CACHE_LOADED=1

# Helper when working in an interactive shell (after source env_nvme_cache.sh).
spark_uv() {
  uv --cache-dir "$_CACHE/uv" "$@"
}
