#!/usr/bin/env bash
# Jetson AGX Orin — Docker + NVIDIA container runtime for infra containers.
# Run ON THE JETSON (once), with sudo.
set -euo pipefail

log() { echo "[jetson-prereqs] $*"; }
die() { echo "[jetson-prereqs] ERROR: $*" >&2; exit 1; }

[[ "$(uname -m)" == "aarch64" ]] || die "Expected aarch64 (Jetson). Got: $(uname -m)"
command -v sudo >/dev/null || die "sudo required"

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker..."
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  log "Added $USER to docker group — log out and back in before next step."
fi

if ! docker info 2>/dev/null | grep -qi nvidia; then
  log "Installing NVIDIA Container Toolkit (Jetson)..."
  if command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit || true
    sudo nvidia-ctk runtime configure --runtime=docker 2>/dev/null || true
    sudo systemctl restart docker 2>/dev/null || sudo service docker restart 2>/dev/null || true
  else
    die "Install nvidia-container-toolkit manually — see deploy/jetson/README.md"
  fi
fi

log "Docker: $(docker --version)"
if command -v nvcc >/dev/null; then
  log "CUDA: $(nvcc --version | tail -1)"
elif [[ -f /etc/nv_tegra_release ]]; then
  log "JetPack: $(head -1 /etc/nv_tegra_release)"
else
  log "WARN: CUDA/JetPack not detected — flash JetPack before bootstrap_compute.sh"
fi

log "Prereqs OK. If docker group was just added, re-login then run bootstrap_compute.sh"
