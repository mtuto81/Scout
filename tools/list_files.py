import os

from tools._paths import safe_home_path

def safe_path(path):
    return safe_home_path(path)

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
