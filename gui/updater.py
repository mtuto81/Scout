import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app_metadata import APP_NAME, get_version
from config import SCOUT_UPDATE_CHECK_INTERVAL_SECONDS, SCOUT_UPDATE_MANIFEST_URL


class UpdateManager(QObject):
    status = Signal(str)
    update_available = Signal(dict)
    no_update = Signal(str)
    downloaded = Signal(dict)
    error = Signal(str)
    restart_requested = Signal()

    def __init__(self):
        super().__init__()
        self.current_version = get_version()
        self.manifest_url = SCOUT_UPDATE_MANIFEST_URL
        self._busy = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)

    def start_listener(self) -> None:
        if not self.manifest_url:
            self.status.emit("Update checks disabled.")
            return

        interval_ms = max(900, SCOUT_UPDATE_CHECK_INTERVAL_SECONDS) * 1000
        self._timer.start(interval_ms)
        QTimer.singleShot(3000, self.check_now)

    @Slot()
    def check_now(self) -> None:
        if not self.manifest_url:
            self.no_update.emit("Set SCOUT_UPDATE_MANIFEST_URL to enable update checks.")
            return
        self._run_background(self._check_for_update)

    @Slot(dict)
    def download_update(self, manifest: Dict[str, Any]) -> None:
        self._run_background(self._download_update, manifest)

    @Slot(dict)
    def apply_update(self, download_info: Dict[str, Any]) -> None:
        try:
            script = self._create_apply_script(download_info)
            subprocess.Popen(["/bin/sh", str(script)], start_new_session=True)
            self.restart_requested.emit()
        except Exception as exc:
            self.error.emit(str(exc))

    def _run_background(self, target, *args) -> None:
        if self._busy:
            self.status.emit("Updater is already busy.")
            return

        self._busy = True

        def runner() -> None:
            try:
                target(*args)
            except Exception as exc:
                self.error.emit(str(exc))
            finally:
                self._busy = False

        threading.Thread(target=runner, daemon=True, name="ScoutUpdater").start()

    def _check_for_update(self) -> None:
        self.status.emit("Checking for updates...")
        manifest = self._fetch_manifest()
        latest_version = str(manifest.get("version", "")).strip()
        if not latest_version:
            raise ValueError("Update manifest is missing 'version'.")

        if _version_tuple(latest_version) <= _version_tuple(self.current_version):
            self.no_update.emit(f"Scout is up to date ({self.current_version}).")
            return

        manifest["current_version"] = self.current_version
        self.update_available.emit(manifest)

    def _download_update(self, manifest: Dict[str, Any]) -> None:
        download_url = str(manifest.get("download_url", "")).strip()
        latest_version = str(manifest.get("version", "")).strip()
        expected_sha256 = str(manifest.get("sha256", "")).strip().lower()

        if not download_url:
            raise ValueError("Update manifest is missing 'download_url'.")
        if not latest_version:
            raise ValueError("Update manifest is missing 'version'.")

        self.status.emit(f"Downloading Scout {latest_version}...")
        updates_dir = _cache_dir() / "updates" / latest_version
        updates_dir.mkdir(parents=True, exist_ok=True)
        archive_path = updates_dir / "Scout-linux-x86_64.tar.gz"

        _download_file(download_url, archive_path)
        actual_sha256 = _sha256_file(archive_path)
        if expected_sha256 and expected_sha256 != "replace-with-release-archive-sha256":
            if actual_sha256 != expected_sha256:
                raise ValueError("Downloaded update failed SHA-256 verification.")

        staged_root = updates_dir / "staged"
        if staged_root.exists():
            shutil.rmtree(staged_root)
        staged_root.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(staged_root, filter="data")

        staged_app_dir = staged_root / APP_NAME
        staged_executable = staged_app_dir / APP_NAME
        if not staged_executable.exists():
            raise ValueError(f"Archive does not contain expected executable: {APP_NAME}/{APP_NAME}")

        staged_executable.chmod(staged_executable.stat().st_mode | 0o111)
        self.downloaded.emit({
            "version": latest_version,
            "archive_path": str(archive_path),
            "sha256": actual_sha256,
            "staged_app_dir": str(staged_app_dir),
            "staged_executable": str(staged_executable),
        })

    def _fetch_manifest(self) -> Dict[str, Any]:
        request = urllib.request.Request(
            self.manifest_url,
            headers={"User-Agent": f"{APP_NAME}/{self.current_version}"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def _create_apply_script(self, download_info: Dict[str, Any]) -> Path:
        target_dir = _current_app_dir()
        staged_app_dir = Path(str(download_info.get("staged_app_dir", ""))).resolve()
        if not staged_app_dir.exists():
            raise FileNotFoundError(f"Staged update was not found: {staged_app_dir}")

        if not _is_packaged_app(target_dir):
            raise RuntimeError("Automatic apply is only available from the packaged Linux executable.")

        if target_dir.name != APP_NAME:
            raise RuntimeError(f"Refusing to update unexpected app directory: {target_dir}")

        script_path = Path(tempfile.gettempdir()) / "scout-apply-update.sh"
        log_path = Path(tempfile.gettempdir()) / "scout-update.log"
        script = f"""#!/bin/sh
set -eu
sleep 1
TARGET={_shell_quote(str(target_dir))}
STAGED={_shell_quote(str(staged_app_dir))}
BACKUP="${{TARGET}}.backup.$(date +%Y%m%d%H%M%S)"
LOG={_shell_quote(str(log_path))}
echo "Applying Scout update..." > "$LOG"
mv "$TARGET" "$BACKUP" >> "$LOG" 2>&1
mv "$STAGED" "$TARGET" >> "$LOG" 2>&1
chmod +x "$TARGET/{APP_NAME}" >> "$LOG" 2>&1
nohup "$TARGET/{APP_NAME}" >> "$LOG" 2>&1 &
"""
        script_path.write_text(script, encoding="utf-8")
        script_path.chmod(0o700)
        return script_path


def _cache_dir() -> Path:
    candidates = []
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        candidates.append(Path(base) / "scout")
    candidates.append(Path.home() / ".cache" / "scout")
    candidates.append(Path(tempfile.gettempdir()) / "scout-cache")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue

    raise RuntimeError("No writable update cache directory is available.")


def _current_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _is_packaged_app(app_dir: Path) -> bool:
    return (app_dir / APP_NAME).exists() and (app_dir / "_internal").exists()


def _download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{get_version()}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_tuple(version: str) -> Tuple[int, ...]:
    parts = []
    for item in version.strip().lstrip("v").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
