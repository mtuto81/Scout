"""Helpers for removing a packaged Scout installation."""

import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "Scout"


def desktop_file_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    data_dir = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return data_dir / "applications" / "scout.desktop"


def installed_app_dir(executable: str | Path | None = None) -> Path | None:
    """Return the packaged app directory, or None when running from source."""
    if not getattr(sys, "frozen", False):
        return None

    executable_path = Path(executable or sys.executable).resolve()
    app_dir = executable_path.parent
    # This guard prevents an accidental broad deletion if the launcher is
    # ever started from an unexpected location.
    if app_dir.name != APP_NAME or app_dir == Path.home() or app_dir == Path("/"):
        return None
    return app_dir


def schedule_uninstall(app_dir: Path, desktop_file: Path | None = None) -> None:
    """Remove Scout after this process exits."""
    desktop_file = desktop_file or desktop_file_path()
    cleanup_script = """\
set -eu
pid=$1
app_dir=$2
desktop_file=$3
while kill -0 "$pid" 2>/dev/null; do
    sleep 0.2
done
rm -rf -- "$app_dir"
rm -f -- "$desktop_file"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$(dirname "$desktop_file")" >/dev/null 2>&1 || true
fi
"""
    subprocess.Popen(
        ["sh", "-c", cleanup_script, "scout-uninstaller", str(os.getpid()), str(app_dir), str(desktop_file)],
        start_new_session=True,
        close_fds=True,
    )
