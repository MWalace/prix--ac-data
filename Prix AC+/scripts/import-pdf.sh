#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/import-config.json"
OUTPUT_FILE="$ROOT_DIR/Data/price-catalog.json"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required but not found. Install Python 3 and try again." >&2
    exit 1
fi

python3 "$ROOT_DIR/scripts/import_pdf.py" \
    --config "$CONFIG_FILE" \
    --output "$OUTPUT_FILE" \
    "$@"
