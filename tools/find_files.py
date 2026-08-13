import fnmatch
import os
from pathlib import Path
from typing import Dict, List

from tools._paths import safe_home_path


SKIP_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}


def find_files(
    name: str,
    path: str = ".",
    max_results: int = 50,
) -> Dict[str, object]:
    """Find files by filename below a directory inside the user's home."""
    name = str(name).strip()
    if not name:
        raise ValueError("name must not be empty")

    root = safe_home_path(path)
    if not root.exists():
        return {"ok": False, "error": f"Search path does not exist: {root}", "matches": []}
    if not root.is_dir():
        return {"ok": False, "error": f"Search path is not a directory: {root}", "matches": []}

    try:
        limit = max(1, min(int(max_results), 200))
    except (TypeError, ValueError):
        limit = 50

    matches: List[str] = []
    pattern = name.casefold()
    for current_root, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(directory for directory in directories if directory not in SKIP_DIRECTORIES)
        for filename in sorted(filenames):
            if not fnmatch.fnmatch(filename.casefold(), pattern):
                continue
            matches.append(str(Path(current_root) / filename))
            if len(matches) >= limit:
                return {
                    "ok": True,
                    "name": name,
                    "root": str(root),
                    "matches": matches,
                    "truncated": True,
                }

    return {
        "ok": True,
        "name": name,
        "root": str(root),
        "matches": matches,
        "truncated": False,
    }


TOOLS = [
    {
        "name": "find_files",
        "description": (
            "Find files by filename under a directory in the user's home directory. "
            "Supports wildcard patterns such as '*.pdf' or 'report*'."
        ),
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Filename or wildcard pattern to find.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory inside the user's home directory. Defaults to home.",
                    "default": ".",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of paths to return, from 1 to 200.",
                    "default": 50,
                },
            },
            "required": ["name"],
        },
        "handler": find_files,
    }
]
