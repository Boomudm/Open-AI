#!/usr/bin/env bash
# Run the backend test suite with the environment this Jetson box needs.
#
# Why this wrapper exists:
#   * APP_ENV on the host is "production" (the box runs the prod stack), but
#     the suite refuses to start with SPARK_PROFILE=test under production.
#   * torch and scikit-learn each bundle their own libgomp; on aarch64 glibc
#     they fail with "cannot allocate memory in static TLS block" unless a
#     libgomp is preloaded before Python starts.
#   * Caches/temp must stay on NVMe (see env_nvme_cache.sh) — eMMC /tmp fills.
#
# Usage (from repo root):
#   scripts/test.sh                 # full suite
#   scripts/test.sh tests/foo.py -k name   # any pytest args pass through
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/env_nvme_cache.sh"

PRELOAD=""
for candidate in \
  /usr/lib/aarch64-linux-gnu/libgomp.so.1 \
  "$ROOT"/.venv/lib/python3.*/site-packages/scikit_learn.libs/libgomp-*.so* \
  "$ROOT"/.venv/lib/python3.*/site-packages/torch/lib/libgomp.so.1; do
  if [[ -e "$candidate" ]]; then
    PRELOAD="${PRELOAD:+$PRELOAD:}$candidate"
  fi
done

PYTEST_ARGS=("$@")
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
  PYTEST_ARGS=(tests -q)
fi

cd "$ROOT"
# optional_static_tls: torch/sklearn load late in a full-suite run, after other
# libraries have consumed glibc's default static-TLS surplus — raise it so
# dlopen'd libgomp/libc10 still fit ("cannot allocate memory in static TLS").
LD_PRELOAD="$PRELOAD" APP_ENV=test \
  GLIBC_TUNABLES=glibc.rtld.optional_static_tls=4096 \
  "$ROOT/.venv/bin/python" -m pytest -p no:cacheprovider "${PYTEST_ARGS[@]}"
