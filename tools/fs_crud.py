import os
from pathlib import Path


WORKSPACE_ROOT = Path(os.environ.get("AGENT_WORKSPACE_ROOT", os.getcwd())).resolve()


def safe_path(path):
    target = (WORKSPACE_ROOT / path).resolve()
    if not str(target).startswith(str(WORKSPACE_ROOT)):
        raise ValueError(f"Path is outside the allowed workspace: {path}")
    return target

def create_file(path, content=""):
    """Creates a new file at the specified path."""
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File created at {target}"

def read_file(path):
    """Reads the content of a file at the specified path."""
    target = safe_path(path)
    with open(target, "r", encoding="utf-8") as f:
        return f.read()

def update_file(path, content):
    """Updates the content of a file at the specified path."""
    target = safe_path(path)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File updated at {target}"

def delete_file(path):
    """Deletes a file at the specified path."""
    target = safe_path(path)
    os.remove(target)
    return f"File deleted at {target}"


TOOLS = [
    {
        "name": "create_file",
        "description": "Create a UTF-8 text file inside the allowed workspace.",
        "risk": "medium",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path."},
                "content": {"type": "string", "description": "File content.", "default": ""},
            },
            "required": ["path"],
        },
        "handler": create_file,
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file from inside the allowed workspace.",
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path."},
            },
            "required": ["path"],
        },
        "handler": read_file,
    },
    {
        "name": "update_file",
        "description": "Overwrite a UTF-8 text file inside the allowed workspace.",
        "risk": "medium",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path."},
                "content": {"type": "string", "description": "New file content."},
            },
            "required": ["path", "content"],
        },
        "handler": update_file,
    },
    {
        "name": "delete_file",
        "description": "Delete a file inside the allowed workspace.",
        "risk": "high",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path."},
            },
            "required": ["path"],
        },
        "handler": delete_file,
    },
]
