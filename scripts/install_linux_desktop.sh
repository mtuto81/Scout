#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
RUNNER="$PROJECT_DIR/scripts/scout"
TEMPLATE="$PROJECT_DIR/packaging/linux/scout.desktop"
DEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DEST_FILE="$DEST_DIR/scout.desktop"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "Missing desktop template: $TEMPLATE" >&2
    exit 1
fi

chmod +x "$RUNNER"
mkdir -p "$DEST_DIR"

sed \
    -e "s|SCOUT_EXEC_PATH|$RUNNER|g" \
    "$TEMPLATE" > "$DEST_FILE"

chmod +x "$DEST_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DEST_DIR" >/dev/null 2>&1 || true
fi

echo "Installed Scout desktop launcher:"
echo "$DEST_FILE"
echo
echo "You can now launch Scout from your app menu."
