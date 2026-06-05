from pathlib import Path


APP_NAME = "Scout"
APP_ID = "io.github.scout.assistant"


def get_version() -> str:
    version_file = Path(__file__).resolve().parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        return "0.0.0"
