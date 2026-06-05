import asyncio
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, Iterable, Optional


BLOCKED_COMMAND_PARTS = (
    "rm -rf /",
    "del /f /s /q c:\\",
    "format ",
    "mkfs",
    "shutdown",
    "reboot",
)

_confirm_callback: Optional[Callable[[str], bool]] = None
_cmd_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ScoutCmd")


def set_confirm_callback(callback: Optional[Callable[[str], bool]]) -> None:
    global _confirm_callback
    _confirm_callback = callback



def confirm_action(command: str) -> bool:
    if _confirm_callback:
        return bool(_confirm_callback(command))

    print(f"\n⚠️ The assistant wants to run this command:\n\n    {command}\n")
    confirm = input("✅ Run it? (yes/no): ").strip().lower()
    return confirm in ("yes", "y")


def looks_blocked(command: str, blocked_parts: Iterable[str] = BLOCKED_COMMAND_PARTS) -> bool:
    lowered = command.lower()
    return any(part in lowered for part in blocked_parts)


def _uses_leading_sudo(command: str) -> bool:
    return command.lstrip().startswith("sudo ")


def _prepare_interactive_sudo(command: str):
    if not _uses_leading_sudo(command):
        return command, None, None

    askpass_path = _create_askpass_script()
    if not askpass_path:
        return (
            command,
            None,
            "sudo needs an interactive password prompt, but neither kdialog nor zenity was found.",
        )

    stripped = command.lstrip()
    prefix_len = len(command) - len(stripped)
    rewritten = command[:prefix_len] + "sudo -A " + stripped[len("sudo "):]
    env = os.environ.copy()
    env["SUDO_ASKPASS"] = askpass_path
    return rewritten, env, None


def _create_askpass_script() -> Optional[str]:
    kdialog = shutil.which("kdialog")
    zenity = shutil.which("zenity")
    if not kdialog and not zenity:
        return None

    script_path = os.path.join(tempfile.gettempdir(), "scout-sudo-askpass.sh")
    if kdialog:
        script = f'#!/bin/sh\nexec "{kdialog}" --password "Scout needs your sudo password"\n'
    else:
        script = f'#!/bin/sh\nexec "{zenity}" --password --title="Scout sudo password"\n'

    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    os.chmod(script_path, 0o700)
    return script_path


def run_cmd(command: str, require_confirm: bool = True, timeout_seconds: int = 30) -> str:
    """Run a shell command after optional confirmation.

    This remains intentionally interactive because it can change the machine.
    """
    if looks_blocked(command):
        return "[CMD blocked: command looks destructive.]"

    if require_confirm:
        if not confirm_action(command):
            return "[CMD aborted by user.]"

    try:
        command, env, sudo_error = _prepare_interactive_sudo(command)
        if sudo_error:
            return f"[CMD blocked: {sudo_error}]"

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
        return result.stdout.strip() or result.stderr.strip()
    except subprocess.TimeoutExpired:
        return f"[CMD timed out after {timeout_seconds}s]"
    except Exception as e:
        return f"[ERROR: {e}]"


async def run_cmd_tool(command: str, require_confirm: bool = True, timeout_seconds: int = 30) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _cmd_executor,
        partial(
            run_cmd,
            command,
            require_confirm=require_confirm,
            timeout_seconds=timeout_seconds,
        ),
    )


TOOLS = [
    {
        "name": "run_cmd",
        "aliases": ["run_cmd_tool"],
        "description": "Run a local shell command. Use read-only inspection commands first. Dangerous commands require user confirmation.",
        "risk": "high",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command to run.",
                },
                "require_confirm": {
                    "type": "boolean",
                    "description": "Whether to ask the user before running the command.",
                    "default": True,
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum runtime before killing the command.",
                    "default": 30,
                },
            },
            "required": ["command"],
        },
        "handler": run_cmd_tool,
    }
]
