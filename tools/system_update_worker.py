import itertools
import os
import shutil
import subprocess
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from tools.cmd import _create_askpass_script, confirm_action


_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_job_counter = itertools.count(1)
_max_output_chars = 12000


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _detect_package_manager(package_manager: str = "auto") -> Optional[str]:
    requested = package_manager.strip().lower()
    if requested and requested != "auto":
        return requested if shutil.which(requested) else None

    for candidate in ("dnf", "apt", "pacman", "zypper"):
        if shutil.which(candidate):
            return candidate
    return None


def _update_steps(package_manager: str) -> Optional[List[List[str]]]:
    if package_manager == "dnf":
        return [["sudo", "-A", "dnf", "upgrade", "--refresh", "-y"]]
    if package_manager == "apt":
        return [
            ["sudo", "-A", "apt", "update"],
            ["sudo", "-A", "apt", "upgrade", "-y"],
        ]
    if package_manager == "pacman":
        return [["sudo", "-A", "pacman", "-Syu", "--noconfirm"]]
    if package_manager == "zypper":
        return [["sudo", "-A", "zypper", "--non-interactive", "update"]]
    return None


def _display_command(steps: List[List[str]]) -> str:
    return " && ".join(" ".join(step).replace("sudo -A", "sudo") for step in steps)


def _job_snapshot(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = dict(_jobs[job_id])
    return job


def _append_output(job_id: str, text: str) -> None:
    if not text:
        return

    with _jobs_lock:
        job = _jobs[job_id]
        output = job.get("output_tail", "") + text
        if len(output) > _max_output_chars:
            output = output[-_max_output_chars:]
        job["output_tail"] = output
        job["updated_at"] = _now()


def _set_job_state(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(updates)
        _jobs[job_id]["updated_at"] = _now()


def _sudo_env() -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    askpass_path = _create_askpass_script()
    if not askpass_path:
        return None, "sudo needs kdialog or zenity for an interactive password prompt."

    env = os.environ.copy()
    env["SUDO_ASKPASS"] = askpass_path
    return env, None


def _run_update_job(job_id: str, steps: List[List[str]], env: Dict[str, str]) -> None:
    _set_job_state(job_id, status="running", started_at=_now())

    try:
        for index, step in enumerate(steps, start=1):
            _set_job_state(
                job_id,
                current_step=index,
                total_steps=len(steps),
                command=" ".join(step).replace("sudo -A", "sudo"),
            )
            _append_output(job_id, f"\n$ {' '.join(step).replace('sudo -A', 'sudo')}\n")

            process = subprocess.Popen(
                step,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            assert process.stdout is not None
            for line in process.stdout:
                _append_output(job_id, line)

            returncode = process.wait()
            _set_job_state(job_id, returncode=returncode)
            if returncode != 0:
                _set_job_state(
                    job_id,
                    status="failed",
                    finished_at=_now(),
                    error=f"Update step {index} exited with code {returncode}.",
                )
                return

        _set_job_state(job_id, status="completed", finished_at=_now(), error="")
    except Exception as exc:
        _set_job_state(
            job_id,
            status="failed",
            finished_at=_now(),
            error=str(exc),
        )


def start_system_update(package_manager: str = "auto") -> Dict[str, Any]:
    """Start a confirmed package update in a background worker thread."""
    manager = _detect_package_manager(package_manager)
    if not manager:
        return {
            "started": False,
            "error": f"Package manager '{package_manager}' was not found.",
        }

    steps = _update_steps(manager)
    if not steps:
        return {
            "started": False,
            "error": f"Package manager '{manager}' is not supported.",
        }

    if not shutil.which("sudo"):
        return {
            "started": False,
            "error": "sudo is required for system updates but was not found.",
        }

    command = _display_command(steps)
    if not confirm_action(command):
        return {
            "started": False,
            "aborted": True,
            "message": "System update was cancelled by the user.",
        }

    env, sudo_error = _sudo_env()
    if sudo_error:
        return {
            "started": False,
            "error": sudo_error,
        }

    job_id = f"update-{next(_job_counter)}"
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "type": "system_update",
            "package_manager": manager,
            "status": "queued",
            "command": command,
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "updated_at": _now(),
            "current_step": 0,
            "total_steps": len(steps),
            "returncode": None,
            "error": "",
            "output_tail": "",
        }

    thread = threading.Thread(
        target=_run_update_job,
        args=(job_id, steps, env),
        name=f"ScoutUpdateWorker-{job_id}",
        daemon=True,
    )
    thread.start()

    return {
        "started": True,
        "job_id": job_id,
        "status": "queued",
        "package_manager": manager,
        "message": "System update started in a background worker. Use get_system_update_status to monitor it.",
    }


def get_system_update_status(job_id: str = "latest") -> Dict[str, Any]:
    """Return status and recent output for a background system update job."""
    with _jobs_lock:
        if job_id == "latest":
            if not _jobs:
                return {"found": False, "error": "No system update jobs exist."}
            job_id = sorted(_jobs.keys(), key=lambda key: int(key.split("-")[-1]))[-1]

        if job_id not in _jobs:
            return {"found": False, "error": f"System update job '{job_id}' was not found."}

    snapshot = _job_snapshot(job_id)
    snapshot["found"] = True
    return snapshot


TOOLS = [
    {
        "name": "start_system_update",
        "description": (
            "Start a Linux system package update in a separate background worker. "
            "This changes the system, requires user confirmation, and should only be used after check_updates."
        ),
        "risk": "admin",
        "parameters": {
            "type": "object",
            "properties": {
                "package_manager": {
                    "type": "string",
                    "description": "Package manager to use: auto, dnf, apt, pacman, or zypper.",
                    "default": "auto",
                },
            },
        },
        "handler": start_system_update,
    },
    {
        "name": "get_system_update_status",
        "description": "Check status and recent output for a background system update job.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Update job id, or latest for the most recent job.",
                    "default": "latest",
                },
            },
        },
        "handler": get_system_update_status,
    },
]
