import os
from pathlib import Path


WORKSPACE_ROOT = Path(os.environ.get("AGENT_WORKSPACE_ROOT", os.getcwd())).resolve()


def safe_path(path):
    target = (WORKSPACE_ROOT / path).resolve()
    if not str(target).startswith(str(WORKSPACE_ROOT)):
        raise ValueError(f"Path is outside the allowed workspace: {path}")
    return target

def list_files(path="."):
    """Lists the files and directories in the specified path."""
    return "\n".join(os.listdir(safe_path(path)))


TOOLS = [
    {
        "name": "list_files",
        "description": "List files and directories at a path.",
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list.",
                    "default": ".",
                }
            },
        },
        "handler": list_files,
    }
]
