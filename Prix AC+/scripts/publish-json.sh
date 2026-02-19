#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MESSAGE="${1:-Mise à jour AppleCare+ FR}"

"$ROOT_DIR/scripts/import-pdf.sh"

git -C "$ROOT_DIR" add "Data/price-catalog.json" "Data/import-report.json" "import-config.json"

git -C "$ROOT_DIR" commit -m "$MESSAGE" || true

git -C "$ROOT_DIR" push
