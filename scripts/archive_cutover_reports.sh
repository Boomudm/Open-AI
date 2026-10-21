#!/usr/bin/env bash
# Archive eval reports for cutover evidence bundle (Phase 16).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GIT_SHA="${GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo local)}"
SOURCE_DIR="${REPORT_DIR:-reports/eval/${GIT_SHA}}"
CUTOVER_DATE="${CUTOVER_DATE:-$(date +%Y%m%d)}"
DEST_DIR="${DEST_DIR:-reports/eval/cutover-${CUTOVER_DATE}}"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "No source reports at $SOURCE_DIR — skipping archive" >&2
  exit 0
fi

mkdir -p "$DEST_DIR"
cp -f "$SOURCE_DIR"/*.json "$DEST_DIR/" 2>/dev/null || true

cat > "$DEST_DIR/manifest.json" <<EOF
{
  "git_sha": "${GIT_SHA}",
  "cutover_date": "${CUTOVER_DATE}",
  "source_dir": "${SOURCE_DIR}",
  "archived_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "Archived cutover eval bundle: $DEST_DIR"
