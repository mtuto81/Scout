import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional


def _run(command: List[str], timeout_seconds: int = 8) -> Dict[str, Any]:
    executable = shutil.which(command[0])
    if not executable:
        return {
            "available": False,
            "command": command,
            "stdout": "",
            "stderr": f"{command[0]} is not installed.",
            "returncode": None,
        }

    try:
        result = subprocess.run(
            [executable] + command[1:],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "available": True,
            "command": command,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "available": True,
            "command": command,
            "stdout": "",
            "stderr": f"Command timed out after {timeout_seconds}s.",
            "returncode": None,
        }
    except Exception as exc:
        return {
            "available": True,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
            "returncode": None,
        }


def _bytes_to_gib(value: int) -> float:
    return round(value / 1024 / 1024 / 1024, 2)


def _os_id() -> str:
    os_release = "/etc/os-release"
    if not os.path.exists(os_release):
        return platform.system().lower()

    values = {}
    with open(os_release, "r", encoding="utf-8") as handle:
        for line in handle:
            if "=" not in line:
                continue
            key, value = line.rstrip().split("=", 1)
            values[key] = value.strip('"')

    return values.get("ID", platform.system()).lower()


def check_disk_space(path: str = "/") -> Dict[str, Any]:
    """Return disk usage for a path without modifying the system."""
    usage = shutil.disk_usage(path)
    percent_used = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0

    if percent_used >= 95:
        status = "critical"
        advice = "Disk is almost full. Avoid installing updates or downloading files until space is freed."
    elif percent_used >= 85:
        status = "warning"
        advice = "Disk space is getting low. Cleaning caches or old files is recommended."
    else:
        status = "ok"
        advice = "Disk space looks healthy."

    return {
        "path": path,
        "total_gib": _bytes_to_gib(usage.total),
        "used_gib": _bytes_to_gib(usage.used),
        "free_gib": _bytes_to_gib(usage.free),
        "percent_used": percent_used,
        "status": status,
        "advice": advice,
    }


def check_network_status() -> Dict[str, Any]:
    """Return read-only network status from common Linux tools."""
    return {
        "network_manager": _run(["nmcli", "general", "status"]),
        "active_connections": _run(["nmcli", "connection", "show", "--active"]),
        "routes": _run(["ip", "route"]),
        "dns": _run(["resolvectl", "dns"]),
    }


def check_bluetooth_status() -> Dict[str, Any]:
    """Return read-only Bluetooth status from rfkill, systemd, and bluetoothctl."""
    return {
        "service": _run(["systemctl", "is-active", "bluetooth"]),
        "rfkill": _run(["rfkill", "list", "bluetooth"]),
        "controller": _run(["bluetoothctl", "show"]),
    }


def check_failed_services() -> Dict[str, Any]:
    """Return failed systemd services without changing service state."""
    return {
        "failed_services": _run(["systemctl", "--failed", "--no-pager", "--plain"]),
    }


def check_updates(timeout_seconds: int = 30) -> Dict[str, Any]:
    """Check for available package updates without installing anything."""
    os_id = _os_id()

    if shutil.which("dnf"):
        command = ["dnf", "check-update"]
        manager = "dnf"
    elif shutil.which("apt"):
        command = ["apt", "list", "--upgradable"]
        manager = "apt"
    elif shutil.which("pacman"):
        command = ["pacman", "-Qu"]
        manager = "pacman"
    elif shutil.which("zypper"):
        command = ["zypper", "list-updates"]
        manager = "zypper"
    else:
        return {
            "os_id": os_id,
            "package_manager": None,
            "result": "No supported package manager was found.",
        }

    result = _run(command, timeout_seconds=timeout_seconds)
    return {
        "os_id": os_id,
        "package_manager": manager,
        "result": result,
        "note": "This only checks for updates. It does not install or change packages.",
    }


TOOLS = [
    {
        "name": "check_disk_space",
        "description": "Safely check disk usage for a path. Prefer this before using shell commands like df.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Filesystem path to check.",
                    "default": "/",
                },
            },
        },
        "handler": check_disk_space,
    },
    {
        "name": "check_network_status",
        "description": "Safely inspect Linux network status, active connections, routes, and DNS.",
        "risk": "read_only",
        "parameters": {"type": "object", "properties": {}},
        "handler": check_network_status,
    },
    {
        "name": "check_bluetooth_status",
        "description": "Safely inspect Linux Bluetooth status, rfkill block state, and controller details.",
        "risk": "read_only",
        "parameters": {"type": "object", "properties": {}},
        "handler": check_bluetooth_status,
    },
    {
        "name": "check_failed_services",
        "description": "Safely list failed systemd services for Linux troubleshooting.",
        "risk": "read_only",
        "parameters": {"type": "object", "properties": {}},
        "handler": check_failed_services,
    },
    {
        "name": "check_updates",
        "description": "Safely check whether Linux package updates are available without installing them.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait for the update check.",
                    "default": 30,
                },
            },
        },
        "handler": check_updates,
    },
]
