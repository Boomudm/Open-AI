#!/usr/bin/env bash
# Install PyTorch with Jetson CUDA into the active .venv.
# Must run ON THE JETSON after: python3.12 -m venv .venv && pip install -e ".[dev]"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

log() { echo "[jetson-torch] $*"; }
die() { echo "[jetson-torch] ERROR: $*" >&2; exit 1; }

[[ "$(uname -m)" == "aarch64" ]] || die "Expected aarch64 Jetson"
[[ -d .venv ]] || die ".venv missing — run bootstrap_compute.sh first (venv step)"

# shellcheck disable=SC1091
source .venv/bin/activate

python -c "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)" 2>/dev/null && HAS_CUDA=1 || HAS_CUDA=0

if [[ "$HAS_CUDA" == "1" ]]; then
  log "PyTorch CUDA already available — skipping"
  python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.get_device_name(0))"
  exit 0
fi

log "Installing NVIDIA PyTorch wheel for Jetson (may take several minutes)..."
pip uninstall -y torch torchvision torchaudio 2>/dev/null || true

JP=""
if [[ -f /etc/nv_tegra_release ]]; then
  JP="$(grep -oP 'R\d+' /etc/nv_tegra_release | head -1 || true)"
fi

# JetPack 6.x (R36.x) — adjust if NVIDIA changes index URLs for your flash.
case "${JP}" in
  R36*|R35*)
    pip install --no-cache-dir torch torchvision \
      --index-url https://developer.download.nvidia.com/compute/redist/jp/v60/
    ;;
  *)
    log "WARN: Unknown JetPack ($JP). Trying JP v60 index..."
    pip install --no-cache-dir torch torchvision \
      --index-url https://developer.download.nvidia.com/compute/redist/jp/v60/ \
      || die "PyTorch install failed. See https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/"
    ;;
esac

python - <<'PY'
import torch
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device", torch.cuda.get_device_name(0))
else:
    raise SystemExit("CUDA still not available after install")
PY

log "PyTorch + CUDA OK"
