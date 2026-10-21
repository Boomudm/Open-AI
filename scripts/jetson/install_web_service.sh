#!/usr/bin/env bash
# Install/update spark-web systemd unit (loads JWT_SECRET from web/.env.local).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UNIT_SRC="$ROOT/deploy/jetson/spark-web.service"
UNIT_DST="/etc/systemd/system/spark-web.service"

[[ -f "$UNIT_SRC" ]] || { echo "Missing $UNIT_SRC"; exit 1; }
[[ -f "$ROOT/web/.env.local" ]] || {
  echo "Missing web/.env.local — copy JWT_SECRET from repo .env first:"
  echo "  grep '^JWT_SECRET=' .env >> web/.env.local"
  exit 1
}

sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable spark-web
sudo systemctl restart spark-web
sleep 2
if ! systemctl is-active --quiet spark-web; then
  echo "spark-web failed — recent logs:" >&2
  journalctl -u spark-web -n 15 --no-pager >&2
  exit 1
fi
echo "spark-web restarted ($(systemctl is-active spark-web))"
echo "Verify: curl -sI https://neospark.kcalsion.com/login | head -1"
