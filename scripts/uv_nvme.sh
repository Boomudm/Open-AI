#!/usr/bin/env bash
# Run uv with caches/temp on repo NVMe (.cache/) — not eMMC /tmp.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/env_nvme_cache.sh"
uv --cache-dir "$ROOT/.cache/uv" "$@"
