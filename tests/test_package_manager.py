import asyncio
import os
import tempfile
from unittest.mock import patch, MagicMock
import pytest

from tools.package_manager import (
    detect_package_managers,
    search_packages,
    check_app_installed,
    install_app,
    remove_app,
    _build_install_cmd,
    _build_remove_cmd,
    _check_blocked_removal,
    _parse_dnf_search,
    _parse_apt_search,
    _parse_pacman_search,
    _parse_zypper_search,
    _parse_flatpak_search,
    _parse_snap_find,
)
from tool_manager import AsyncToolManager


class TestDetectPackageManagers:
    def test_detect_fedora_with_dnf_and_flatpak(self):
        os_release = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=42\n'
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(os_release)
            f.flush()
            temp_path = f.name

        try:
            with patch("shutil.which", side_effect=lambda binary: f"/usr/bin/{binary}" if binary in ("dnf", "flatpak") else None):
                res = detect_package_managers(os_release_path=temp_path)
                assert res["primary_native_manager"] == "dnf"
                assert "dnf" in res["native_managers"]
                assert "flatpak" in res["universal_managers"]
                assert res["os_info"]["id"] == "fedora"
        finally:
            os.unlink(temp_path)

    def test_detect_ubuntu_with_apt_and_snap(self):
        os_release = 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n'
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(os_release)
            f.flush()
            temp_path = f.name

        try:
            with patch("shutil.which", side_effect=lambda binary: f"/usr/bin/{binary}" if binary in ("apt", "apt-get", "snap") else None):
                res = detect_package_managers(os_release_path=temp_path)
                assert res["primary_native_manager"] == "apt"
                assert "apt" in res["native_managers"]
                assert "snap" in res["universal_managers"]
                assert res["os_info"]["id"] == "ubuntu"
        finally:
            os.unlink(temp_path)

    def test_detect_arch_with_pacman(self):
        os_release = 'NAME="Arch Linux"\nID=arch\n'
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(os_release)
            f.flush()
            temp_path = f.name

        try:
            with patch("shutil.which", side_effect=lambda binary: f"/usr/bin/{binary}" if binary in ("pacman",) else None):
                res = detect_package_managers(os_release_path=temp_path)
                assert res["primary_native_manager"] == "pacman"
                assert "pacman" in res["native_managers"]
                assert res["universal_managers"] == []
        finally:
            os.unlink(temp_path)

    def test_detect_opensuse_with_zypper(self):
        os_release = 'NAME="openSUSE Tumbleweed"\nID=opensuse-tumbleweed\nID_LIKE="opensuse suse"\n'
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(os_release)
            f.flush()
            temp_path = f.name

        try:
            with patch("shutil.which", side_effect=lambda binary: f"/usr/bin/{binary}" if binary in ("zypper",) else None):
                res = detect_package_managers(os_release_path=temp_path)
                assert res["primary_native_manager"] == "zypper"
                assert "zypper" in res["native_managers"]
        finally:
            os.unlink(temp_path)


class TestSearchPackages:
    def test_search_empty_query(self):
        res = search_packages("")
        assert res["success"] is False
        assert "empty" in res["error"].lower()

    def test_search_injection_blocked(self):
        for bad in ["vlc; rm -rf /", "htop | bash", "curl`whoami`", "vlc$(id)"]:
            res = search_packages(bad)
            assert res["success"] is False
            assert "invalid" in res["error"].lower()

    def test_parse_dnf_search(self):
        stdout = """
====================== Name Exactly Matched: vlc ======================
vlc.x86_64 : The cross-platform open-source multimedia player
===================== Name & Summary Matched: vlc =====================
vlc-core.x86_64 : VLC media player core
"""
        results = _parse_dnf_search(stdout, max_results=10)
        assert len(results) == 2
        assert results[0]["name"] == "vlc"
        assert "cross-platform" in results[0]["summary"]
        assert results[0]["manager"] == "dnf"
        assert results[1]["name"] == "vlc-core"

    def test_parse_apt_search(self):
        stdout = """
vlc - multimedia player and streamer
vlc-bin - multimedia player and streamer (binaries)
"""
        results = _parse_apt_search(stdout, max_results=10)
        assert len(results) == 2
        assert results[0]["name"] == "vlc"
        assert results[0]["summary"] == "multimedia player and streamer"
        assert results[0]["manager"] == "apt"

    def test_parse_pacman_search(self):
        stdout = """
extra/vlc 3.0.21-1 [installed]
    Multi-platform MPEG, VCD/DVD, and DivX player
extra/vlc-plugin-fluidsynth 3.0.21-1
    FluidSynth plugin for VLC
"""
        results = _parse_pacman_search(stdout, max_results=10)
        assert len(results) == 2
        assert results[0]["name"] == "vlc"
        assert results[0]["full_name"] == "extra/vlc"
        assert "Multi-platform" in results[0]["summary"]
        assert results[0]["manager"] == "pacman"

    def test_parse_flatpak_search(self):
        stdout = "org.videolan.VLC\tVLC\tVLC media player\t3.0.20\tstable\tflathub"
        results = _parse_flatpak_search(stdout, max_results=10)
        assert len(results) == 1
        assert results[0]["name"] == "org.videolan.VLC"
        assert results[0]["full_name"] == "VLC"
        assert results[0]["summary"] == "VLC media player"
        assert results[0]["manager"] == "flatpak"

    def test_parse_snap_find(self):
        stdout = """Name   Version   Publisher   Notes   Summary
vlc    3.0.20    videolan    -       The ultimate media player
"""
        results = _parse_snap_find(stdout, max_results=10)
        assert len(results) == 1
        assert results[0]["name"] == "vlc"
        assert results[0]["summary"] == "The ultimate media player"
        assert results[0]["manager"] == "snap"


class TestCheckAppInstalled:
    def test_check_empty_package(self):
        res = check_app_installed("")
        assert res["installed"] is False
        assert "empty" in res["error"].lower()

    def test_check_invalid_chars(self):
        res = check_app_installed("vlc; rm -rf")
        assert res["installed"] is False
        assert "invalid" in res["error"].lower()

    def test_check_rpm_installed(self):
        with patch("tools.package_manager.detect_package_managers", return_value={
            "primary_native_manager": "dnf",
            "native_managers": ["dnf"],
            "universal_managers": [],
            "all_available": ["dnf"],
        }):
            with patch("tools.package_manager._check_rpm_installed", return_value=(True, "3.14.7-1.fc44", "Python interpreter")):
                res = check_app_installed("python3")
                assert res["installed"] is True
                assert res["package"] == "python3"
                assert res["version"] == "3.14.7-1.fc44"
                assert res["manager"] == "dnf"
                assert res["summary"] == "Python interpreter"

    def test_check_dpkg_installed(self):
        with patch("tools.package_manager.detect_package_managers", return_value={
            "primary_native_manager": "apt",
            "native_managers": ["apt"],
            "universal_managers": [],
            "all_available": ["apt"],
        }):
            with patch("tools.package_manager._check_dpkg_installed", return_value=(True, "3.12.3-0ubuntu1", "Interactive high-level object-oriented language")):
                res = check_app_installed("python3", package_manager="apt")
                assert res["installed"] is True
                assert res["version"] == "3.12.3-0ubuntu1"
                assert res["manager"] == "apt"

    def test_check_not_installed(self):
        with patch("tools.package_manager.detect_package_managers", return_value={
            "primary_native_manager": "dnf",
            "native_managers": ["dnf"],
            "universal_managers": ["flatpak"],
            "all_available": ["dnf", "flatpak"],
        }):
            with patch("tools.package_manager._check_rpm_installed", return_value=(False, "", "")):
                with patch("tools.package_manager._check_flatpak_installed", return_value=(False, "", "")):
                    with patch("shutil.which", return_value=None):
                        res = check_app_installed("nonexistent_app_12345")
                        assert res["installed"] is False
                        assert res["package"] == "nonexistent_app_12345"
                        assert res["manager"] is None


class TestInstallApp:
    def test_install_empty_packages(self):
        res = install_app([])
        assert res["success"] is False
        assert "empty" in res["error"].lower()

    def test_install_invalid_name(self):
        res = install_app(["vlc; rm -rf /"])
        assert res["success"] is False
        assert "invalid" in res["error"].lower()

    def test_build_install_commands(self):
        assert _build_install_cmd("dnf", ["vlc", "htop"]) == ["sudo", "-A", "dnf", "install", "-y", "vlc", "htop"]
        assert _build_install_cmd("apt", ["vlc"]) == ["sudo", "-A", "apt-get", "install", "-y", "vlc"]
        assert _build_install_cmd("pacman", ["vlc"]) == ["sudo", "-A", "pacman", "-S", "--noconfirm", "vlc"]
        assert _build_install_cmd("zypper", ["vlc"]) == ["sudo", "-A", "zypper", "--non-interactive", "install", "vlc"]
        assert _build_install_cmd("apk", ["vlc"]) == ["sudo", "-A", "apk", "add", "vlc"]
        assert _build_install_cmd("flatpak", ["org.videolan.VLC"]) == ["flatpak", "install", "-y", "org.videolan.VLC"]
        assert _build_install_cmd("snap", ["vlc"]) == ["sudo", "-A", "snap", "install", "vlc"]

    def test_install_user_cancelled(self):
        with patch("tools.package_manager._resolve_manager", return_value=("dnf", None)):
            with patch("tools.package_manager.confirm_action", return_value=False):
                res = install_app(["vlc"])
                assert res["success"] is False
                assert res["aborted"] is True
                assert "cancelled" in res["message"].lower()

    def test_install_success(self):
        with patch("tools.package_manager._resolve_manager", return_value=("dnf", None)):
            with patch("tools.package_manager.confirm_action", return_value=True):
                with patch("tools.package_manager._prepare_cmd_env", return_value=({}, None)):
                    with patch("tools.package_manager._run_cmd", return_value={"returncode": 0, "stdout": "Complete!", "stderr": ""}):
                        res = install_app(["vlc"])
                        assert res["success"] is True
                        assert res["returncode"] == 0
                        assert "Successfully installed vlc" in res["message"]

    def test_install_failure(self):
        with patch("tools.package_manager._resolve_manager", return_value=("dnf", None)):
            with patch("tools.package_manager.confirm_action", return_value=True):
                with patch("tools.package_manager._prepare_cmd_env", return_value=({}, None)):
                    with patch("tools.package_manager._run_cmd", return_value={"returncode": 1, "stdout": "", "stderr": "No match for argument: vlc"}):
                        res = install_app(["vlc"])
                        assert res["success"] is False
                        assert res["returncode"] == 1


class TestRemoveApp:
    def test_remove_blocked_system_packages(self):
        for core in ("systemd", "systemd-udev", "glibc", "glibc-common", "kernel", "kernel-core", "sudo", "bash", "coreutils", "dnf", "apt", "pacman", "@core"):
            blocked, msg = _check_blocked_removal([core])
            assert blocked is True, f"Expected {core} to be blocked from removal"
            assert "cannot be removed" in msg or "essential" in msg

    def test_remove_blocked_in_remove_app_call(self):
        res = remove_app(["systemd"])
        assert res["success"] is False
        assert res["blocked"] is True
        assert "essential" in res["error"] or "cannot be removed" in res["error"]

    def test_build_remove_commands(self):
        assert _build_remove_cmd("dnf", ["vlc"]) == ["sudo", "-A", "dnf", "remove", "-y", "vlc"]
        assert _build_remove_cmd("apt", ["vlc"], purge=False) == ["sudo", "-A", "apt-get", "remove", "-y", "vlc"]
        assert _build_remove_cmd("apt", ["vlc"], purge=True) == ["sudo", "-A", "apt-get", "purge", "-y", "vlc"]
        assert _build_remove_cmd("pacman", ["vlc"], purge=False) == ["sudo", "-A", "pacman", "-R", "--noconfirm", "vlc"]
        assert _build_remove_cmd("pacman", ["vlc"], purge=True) == ["sudo", "-A", "pacman", "-Rns", "--noconfirm", "vlc"]
        assert _build_remove_cmd("flatpak", ["org.videolan.VLC"], purge=True) == ["flatpak", "uninstall", "-y", "org.videolan.VLC", "--delete-data"]
        assert _build_remove_cmd("snap", ["vlc"], purge=True) == ["sudo", "-A", "snap", "remove", "vlc", "--purge"]

    def test_remove_user_cancelled(self):
        with patch("tools.package_manager._resolve_manager", return_value=("dnf", None)):
            with patch("tools.package_manager.confirm_action", return_value=False):
                res = remove_app(["vlc"])
                assert res["success"] is False
                assert res["aborted"] is True
                assert "cancelled" in res["message"].lower()

    def test_remove_success(self):
        with patch("tools.package_manager._resolve_manager", return_value=("dnf", None)):
            with patch("tools.package_manager.confirm_action", return_value=True):
                with patch("tools.package_manager._prepare_cmd_env", return_value=({}, None)):
                    with patch("tools.package_manager._run_cmd", return_value={"returncode": 0, "stdout": "Removed: vlc", "stderr": ""}):
                        res = remove_app(["vlc"])
                        assert res["success"] is True
                        assert "Successfully removed vlc" in res["message"]


class TestToolManagerIntegration:
    def test_tool_manager_discovers_all_package_tools(self):
        manager = AsyncToolManager()
        names = manager.get_tool_names()
        assert "detect_package_managers" in names
        assert "search_packages" in names
        assert "check_app_installed" in names
        assert "install_app" in names
        assert "remove_app" in names

    def test_execute_detect_package_managers(self):
        manager = AsyncToolManager()
        result = asyncio.run(manager.execute_tool_call("detect_package_managers", {}))
        assert result["success"] is True
        assert result["tool"] == "detect_package_managers"
        assert "primary_native_manager" in result["result"]
