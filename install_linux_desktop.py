import os
import shutil
import stat
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
RUNNER = PROJECT_DIR / "scripts" / "scout"
BUILT_EXECUTABLE = PROJECT_DIR / "dist" / "Scout" / "Scout"
TEMPLATE = PROJECT_DIR / "packaging" / "linux" / "scout.desktop"
DEST_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
DEST_FILE = DEST_DIR / "scout.desktop"


def make_executable(path: Path) -> None:
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_desktop_launcher() -> None:
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Missing desktop template: {TEMPLATE}")

    if BUILT_EXECUTABLE.exists():
        exec_path = BUILT_EXECUTABLE
    else:
        if not RUNNER.exists():
            raise FileNotFoundError(f"Missing runner: {RUNNER}")
        exec_path = RUNNER

    make_executable(exec_path)
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    desktop_text = TEMPLATE.read_text(encoding="utf-8")
    desktop_text = desktop_text.replace("SCOUT_EXEC_PATH", str(exec_path))
    DEST_FILE.write_text(desktop_text, encoding="utf-8")
    make_executable(DEST_FILE)

    update_desktop_database = shutil.which("update-desktop-database")
    if update_desktop_database:
        subprocess.run(
            [update_desktop_database, str(DEST_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    print("Installed Scout desktop launcher:")
    print(DEST_FILE)
    print(f"Exec: {exec_path}")
    print()
    print("You can now launch Scout from your app menu.")


if __name__ == "__main__":
    install_desktop_launcher()
