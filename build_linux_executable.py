import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_DIR / "packaging" / "linux" / "scout_pyinstaller.spec"
OUTPUT_EXE = PROJECT_DIR / "dist" / "Scout" / "Scout"


def require_pyinstaller() -> None:
    if shutil.which("pyinstaller"):
        return

    try:
        __import__("PyInstaller")
    except Exception as exc:
        raise RuntimeError(
            "PyInstaller is required to build the Linux executable. "
            "Install it with: python -m pip install pyinstaller"
        ) from exc


def build() -> None:
    require_pyinstaller()

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(SPEC_FILE),
    ]
    subprocess.run(command, cwd=PROJECT_DIR, check=True)

    if not OUTPUT_EXE.exists():
        raise FileNotFoundError(f"Build finished, but executable was not found: {OUTPUT_EXE}")

    print()
    print("Scout Linux executable built:")
    print(OUTPUT_EXE)
    print()
    print("Run it with:")
    print(f"{OUTPUT_EXE}")


if __name__ == "__main__":
    build()
