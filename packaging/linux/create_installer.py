import argparse
from pathlib import Path


INSTALLER_HEADER = """#!/bin/sh
set -eu

APP_NAME="Scout"
INSTALL_DIR="${SCOUT_INSTALL_DIR:-$HOME/.local/opt/Scout}"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/scout.desktop"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

ARCHIVE_LINE="$(awk '/^__SCOUT_ARCHIVE_BELOW__$/ { print NR + 1; exit 0; }' "$0")"
if [ -z "$ARCHIVE_LINE" ]; then
    echo "Installer archive marker was not found." >&2
    exit 1
fi

echo "Installing Scout..."
tail -n +"$ARCHIVE_LINE" "$0" | tar -xz -C "$TMP_DIR"

if [ ! -f "$TMP_DIR/$APP_NAME/$APP_NAME" ]; then
    echo "Installer archive does not contain $APP_NAME/$APP_NAME." >&2
    exit 1
fi

mkdir -p "$(dirname "$INSTALL_DIR")"
if [ -e "$INSTALL_DIR" ]; then
    BACKUP="$INSTALL_DIR.backup.$(date +%Y%m%d%H%M%S)"
    echo "Existing install found. Moving it to $BACKUP"
    mv "$INSTALL_DIR" "$BACKUP"
fi

mv "$TMP_DIR/$APP_NAME" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/$APP_NAME"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Scout
GenericName=Linux AI Assistant
Comment=Scout native Linux IT assistant
Exec=$INSTALL_DIR/$APP_NAME
Icon=applications-system
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=Scout
DESKTOP
chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Scout installed to:"
echo "$INSTALL_DIR"
echo
echo "Desktop launcher installed to:"
echo "$DESKTOP_FILE"
echo
echo "Run Scout with:"
echo "$INSTALL_DIR/$APP_NAME"
exit 0

__SCOUT_ARCHIVE_BELOW__
"""


def create_installer(archive_path: Path, output_path: Path) -> None:
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    output_path.write_bytes(
        INSTALLER_HEADER.encode("utf-8") + archive_path.read_bytes()
    )
    output_path.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Scout Linux .run installer.")
    parser.add_argument("archive", type=Path, help="Scout-linux-x86_64.tar.gz path")
    parser.add_argument("output", type=Path, help="Output .run installer path")
    args = parser.parse_args()
    create_installer(args.archive, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
