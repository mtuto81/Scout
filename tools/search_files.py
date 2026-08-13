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
MAX_FILE_BYTES = 5 * 1024 * 1024


def _is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
    except OSError:
        return True
    return b"\x00" in sample


def search_files(
    query: str,
    path: str = ".",
    filename_pattern: str = "*",
    case_sensitive: bool = False,
    max_results: int = 50,
) -> Dict[str, object]:
    """Search readable text files below a directory for a literal string."""
    query = str(query)
    if not query:
        raise ValueError("query must not be empty")

    try:
        root = safe_home_path(path)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"Invalid search path: {exc}", "matches": []}

    if not root.exists():
        return {"ok": False, "error": f"Search path does not exist: {root}", "matches": []}
    if not root.is_dir():
        return {"ok": False, "error": f"Search path is not a directory: {root}", "matches": []}

    try:
        limit = max(1, min(int(max_results), 200))
    except (TypeError, ValueError):
        limit = 50

    needle = query if case_sensitive else query.casefold()
    matches: List[Dict[str, object]] = []
    files_scanned = 0

    for current_root, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in SKIP_DIRECTORIES)
        for filename in sorted(filenames):
            if not fnmatch.fnmatch(filename, filename_pattern):
                continue
            file_path = Path(current_root) / filename
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES or _is_probably_binary(file_path):
                    continue
                files_scanned += 1
                with file_path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        haystack = line if case_sensitive else line.casefold()
                        if needle not in haystack:
                            continue
                        matches.append({
                            "file": str(file_path),
                            "line": line_number,
                            "text": line.rstrip()[:500],
                        })
                        if len(matches) >= limit:
                            return {
                                "ok": True,
                                "query": query,
                                "root": str(root),
                                "files_scanned": files_scanned,
                                "matches": matches,
                                "truncated": True,
                            }
            except (OSError, UnicodeError):
                continue

    return {
        "ok": True,
        "query": query,
        "root": str(root),
        "files_scanned": files_scanned,
        "matches": matches,
        "truncated": False,
    }


TOOLS = [
    {
        "name": "search_files",
        "description": (
            "Search text files by content below a directory. Use an explicit path when possible. "
            "This is read-only and returns matching file paths, line numbers, and excerpts."
        ),
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Literal text to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory inside the user's home directory. Defaults to the home directory.",
                    "default": ".",
                },
                "filename_pattern": {
                    "type": "string",
                    "description": "Optional shell-style filename filter, such as '*.py'.",
                    "default": "*",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether matching should respect letter case.",
                    "default": False,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching lines to return, from 1 to 200.",
                    "default": 50,
                },
            },
            "required": ["query"],
        },
        "handler": search_files,
    }
]
