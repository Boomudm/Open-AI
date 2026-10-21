#!/usr/bin/env bash
# Launch the GPU inference sidecar (dense embed + rerank on the Jetson GPU).
# Used both by the systemd unit (spark-gpu-sidecar.service) and for manual runs.
set -euo pipefail

cd "$(dirname "$0")"

export HF_HOME="$PWD/hf-cache"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
# Pin to the Orin GPU.
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

HOST="${SIDECAR_HOST:-0.0.0.0}"
PORT="${SIDECAR_PORT:-8137}"

exec .venv/bin/uvicorn server:app --host "$HOST" --port "$PORT" --workers 1
