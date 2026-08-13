"""Shared path boundary for Scout's filesystem tools."""

from pathlib import Path


HOME_ROOT = Path.home().resolve()


def safe_home_path(path: str | Path) -> Path:
    """Resolve a relative or absolute path, allowing only paths below home."""
    requested = Path(path).expanduser()
    target = (HOME_ROOT / requested).resolve()
    try:
        target.relative_to(HOME_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path is outside the allowed home directory: {path}") from exc
    return target
