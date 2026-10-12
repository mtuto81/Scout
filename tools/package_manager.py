import os
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union

from tools.cmd import _create_askpass_script, confirm_action
from tools.packagekit_client import PackageKitClient, is_packagekit_available, parse_package_id


SAFE_PKG_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\+@:/]+$")
SAFE_QUERY_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\+\*\?@:/ ]+$")

SUPPORTED_NATIVE_MANAGERS = ("dnf", "apt", "pacman", "zypper", "apk")
SUPPORTED_UNIVERSAL_MANAGERS = ("flatpak", "snap")
ALL_SUPPORTED_MANAGERS = SUPPORTED_NATIVE_MANAGERS + SUPPORTED_UNIVERSAL_MANAGERS + ("packagekit",)

DISTRO_MANAGER_MAP = {
    "fedora": "dnf",
    "rhel": "dnf",
    "centos": "dnf",
    "rocky": "dnf",
    "almalinux": "dnf",
    "amzn": "dnf",
    "debian": "apt",
    "ubuntu": "apt",
    "linuxmint": "apt",
    "pop": "apt",
    "elementary": "apt",
    "kali": "apt",
    "raspbian": "apt",
    "arch": "pacman",
    "manjaro": "pacman",
    "endeavouros": "pacman",
    "garuda": "pacman",
    "artix": "pacman",
    "opensuse": "zypper",
    "opensuse-tumbleweed": "zypper",
    "opensuse-leap": "zypper",
    "sles": "zypper",
    "suse": "zypper",
    "alpine": "apk",
}

BLOCKED_CORE_PACKAGES = {
    "glibc",
    "glibc-common",
    "glibc-all-langpacks",
    "systemd",
    "systemd-libs",
    "systemd-udev",
    "systemd-pam",
    "kernel",
    "kernel-core",
    "kernel-modules",
    "kernel-modules-extra",
    "linux-image",
    "linux-headers",
    "linux-firmware",
    "sudo",
    "bash",
    "sh",
    "coreutils",
    "coreutils-common",
    "basesystem",
    "filesystem",
    "login",
    "pam",
    "shadow-utils",
    "util-linux",
    "rpm",
    "dpkg",
    "pacman",
    "dnf",
    "dnf5",
    "apt",
    "zypper",
    "apk",
    "@core",
    "@base",
    "@standard",
    "grub",
    "grub2",
    "polkit",
    "dbus",
    "dbus-broker",
    "dbus-daemon",
    "glib2",
    "libgcc",
    "libstdc++",
}


def _read_os_release(os_release_path: str = "/etc/os-release") -> Dict[str, str]:
    paths = [os_release_path, "/usr/lib/os-release"]
    for path in paths:
        if os.path.exists(path):
            values: Dict[str, str] = {}
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line or "=" not in line or line.startswith("#"):
                            continue
                        key, value = line.split("=", 1)
                        values[key.strip()] = value.strip().strip('"').strip("'")
                return values
            except Exception:
                pass
    return {
        "ID": platform.system().lower(),
        "NAME": platform.system(),
        "VERSION_ID": platform.release(),
    }


def _run_cmd(cmd: List[str], timeout_seconds: int = 15, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    executable = shutil.which(cmd[0])
    if not executable:
        return {
            "available": False,
            "stdout": "",
            "stderr": f"Executable '{cmd[0]}' is not installed or not in PATH.",
            "returncode": -1,
        }

    try:
        result = subprocess.run(
            [executable] + cmd[1:],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            check=False,
        )
        return {
            "available": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "available": True,
            "stdout": "",
            "stderr": f"Command '{' '.join(cmd)}' timed out after {timeout_seconds}s.",
            "returncode": -1,
        }
    except Exception as exc:
        return {
            "available": True,
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
        }


def detect_package_managers(os_release_path: str = "/etc/os-release") -> Dict[str, Any]:
    """Detect available Linux package managers, PackageKit D-Bus, and primary manager."""
    os_info = _read_os_release(os_release_path)
    os_id = os_info.get("ID", "").lower()
    id_like = os_info.get("ID_LIKE", "").lower().split()

    native_managers: List[str] = []
    for manager in SUPPORTED_NATIVE_MANAGERS:
        binary = "apt-get" if manager == "apt" else manager
        if shutil.which(binary) or shutil.which(manager):
            native_managers.append(manager)

    universal_managers: List[str] = []
    for manager in SUPPORTED_UNIVERSAL_MANAGERS:
        if shutil.which(manager):
            universal_managers.append(manager)

    pk_available = is_packagekit_available()

    primary_native = None
    if os_id in DISTRO_MANAGER_MAP:
        candidate = DISTRO_MANAGER_MAP[os_id]
        if candidate in native_managers:
            primary_native = candidate

    if not primary_native:
        for like in id_like:
            if like in DISTRO_MANAGER_MAP:
                candidate = DISTRO_MANAGER_MAP[like]
                if candidate in native_managers:
                    primary_native = candidate
                    break

    if not primary_native and native_managers:
        primary_native = native_managers[0]

    all_available = list(native_managers)
    if pk_available:
        all_available.append("packagekit")
    all_available.extend(universal_managers)

    return {
        "primary_native_manager": primary_native,
        "packagekit_available": pk_available,
        "native_managers": native_managers,
        "universal_managers": universal_managers,
        "all_available": all_available,
        "os_info": {
            "id": os_id,
            "name": os_info.get("NAME", platform.system()),
            "version_id": os_info.get("VERSION_ID", ""),
            "id_like": os_info.get("ID_LIKE", ""),
            "pretty_name": os_info.get("PRETTY_NAME", ""),
        },
    }


def _resolve_manager(
    package_manager: str = "auto",
    allow_universal: bool = True,
    os_release_path: str = "/etc/os-release",
) -> Tuple[Optional[str], Optional[str]]:
    requested = package_manager.strip().lower()
    detection = detect_package_managers(os_release_path=os_release_path)

    if requested and requested != "auto":
        if requested not in ALL_SUPPORTED_MANAGERS:
            return None, f"Unsupported package manager '{requested}'. Supported: {', '.join(ALL_SUPPORTED_MANAGERS)}"
        if requested not in detection["all_available"]:
            return None, f"Package manager '{requested}' is not installed or available on this system."
        return requested, None

    # Auto resolution preference
    if detection.get("packagekit_available"):
        return "packagekit", None

    primary = detection.get("primary_native_manager")
    if primary:
        return primary, None

    if allow_universal and detection.get("universal_managers"):
        return detection["universal_managers"][0], None

    return None, "No supported package manager was detected on this system."


def _normalize_package_list(packages: Union[str, List[str]]) -> List[str]:
    if isinstance(packages, str):
        raw = packages.replace(",", " ").split()
    elif isinstance(packages, (list, tuple)):
        raw = []
        for item in packages:
            if isinstance(item, str):
                raw.extend(item.replace(",", " ").split())
    else:
        raw = []
    return [p.strip() for p in raw if p.strip()]


def _validate_package_names(packages: List[str]) -> Tuple[bool, Optional[str]]:
    if not packages:
        return False, "Package list cannot be empty."
    for pkg in packages:
        if not SAFE_PKG_PATTERN.match(pkg):
            return False, f"Package name '{pkg}' contains invalid characters."
    return True, None


def _check_blocked_removal(packages: List[str]) -> Tuple[bool, Optional[str]]:
    for pkg in packages:
        lowered = pkg.lower()
        if lowered in BLOCKED_CORE_PACKAGES:
            return True, f"Removal blocked: package '{pkg}' is essential to system operation."
        for core in ("systemd", "kernel", "glibc", "linux-image"):
            if lowered.startswith(core) and (len(lowered) == len(core) or lowered[len(core)] in ("-", "_", ".")):
                return True, f"Removal blocked: core component '{pkg}' cannot be removed."
    return False, None


def _parse_dnf_search(stdout: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    lines = stdout.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("=") or line.startswith("Last metadata"):
            continue
        if " : " in line:
            name_arch, summary = line.split(" : ", 1)
            pkg_name = name_arch.split(".")[0].strip()
            results.append({
                "name": pkg_name,
                "full_name": name_arch.strip(),
                "summary": summary.strip(),
                "manager": "dnf",
            })
            if len(results) >= max_results:
                break
    return results


def _parse_apt_search(stdout: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    lines = stdout.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if " - " in line:
            pkg_name, summary = line.split(" - ", 1)
            results.append({
                "name": pkg_name.strip(),
                "full_name": pkg_name.strip(),
                "summary": summary.strip(),
                "manager": "apt",
            })
            if len(results) >= max_results:
                break
    return results


def _parse_pacman_search(stdout: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    lines = stdout.splitlines()
    i = 0
    while i < len(lines) and len(results) < max_results:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        parts = line.split()
        if parts:
            repo_name = parts[0]
            pkg_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
            summary = ""
            if i + 1 < len(lines) and lines[i + 1].startswith("    "):
                summary = lines[i + 1].strip()
                i += 1
            results.append({
                "name": pkg_name,
                "full_name": repo_name,
                "summary": summary,
                "manager": "pacman",
            })
        i += 1
    return results


def _parse_zypper_search(stdout: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    lines = stdout.splitlines()
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3 and parts[1] != "Name":
                results.append({
                    "name": parts[1],
                    "full_name": parts[1],
                    "summary": parts[2] if len(parts) > 2 else "",
                    "manager": "zypper",
                })
                if len(results) >= max_results:
                    break
    return results


def _parse_flatpak_search(stdout: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    lines = stdout.splitlines()
    for line in lines:
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= 2 and parts[0] != "Application ID":
            app_id = parts[0]
            app_name = parts[1] if len(parts) > 1 else app_id
            summary = parts[2] if len(parts) > 2 else ""
            results.append({
                "name": app_id,
                "full_name": app_name,
                "summary": summary,
                "manager": "flatpak",
            })
            if len(results) >= max_results:
                break
    return results


def _parse_snap_find(stdout: str, max_results: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    lines = stdout.splitlines()
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=4)
        if len(parts) >= 1:
            pkg_name = parts[0]
            summary = parts[4] if len(parts) >= 5 else ""
            results.append({
                "name": pkg_name,
                "full_name": pkg_name,
                "summary": summary,
                "manager": "snap",
            })
            if len(results) >= max_results:
                break
    return results


def search_packages(
    query: str,
    package_manager: str = "auto",
    max_results: int = 20,
    os_release_path: str = "/etc/os-release",
) -> Dict[str, Any]:
    """Search for packages/applications by name/keyword using PackageKit D-Bus or native CLI."""
    query = query.strip()
    if not query:
        return {"success": False, "error": "Search query cannot be empty.", "results": []}

    if not SAFE_QUERY_PATTERN.match(query):
        return {
            "success": False,
            "error": "Query contains invalid or prohibited characters.",
            "results": [],
        }

    max_results = max(1, min(max_results, 50))
    req_manager = package_manager.strip().lower()

    # PackageKit D-Bus direct search path
    if req_manager in ("packagekit", "auto") and is_packagekit_available():
        try:
            client = PackageKitClient(timeout_seconds=20)
            res = client.search_names(query, max_results=max_results)
            if res.get("success"):
                return res
        except Exception:
            pass
        if req_manager == "packagekit":
            return {"success": False, "error": "PackageKit D-Bus search failed.", "results": []}

    manager, error = _resolve_manager(package_manager, allow_universal=True, os_release_path=os_release_path)
    if error or not manager:
        return {"success": False, "error": error or "Package manager not found.", "results": []}

    if manager == "dnf":
        cmd = ["dnf", "search", query]
    elif manager == "apt":
        cmd = ["apt-cache", "search", query]
    elif manager == "pacman":
        cmd = ["pacman", "-Ss", query]
    elif manager == "zypper":
        cmd = ["zypper", "--non-interactive", "search", query]
    elif manager == "apk":
        cmd = ["apk", "search", "-v", query]
    elif manager == "flatpak":
        cmd = ["flatpak", "search", "--columns=application,name,description", query]
    elif manager == "snap":
        cmd = ["snap", "find", query]
    else:
        return {"success": False, "error": f"Search not implemented for manager '{manager}'.", "results": []}

    run_res = _run_cmd(cmd, timeout_seconds=20)
    if run_res["returncode"] != 0 and not run_res["stdout"]:
        return {
            "success": False,
            "query": query,
            "package_manager": manager,
            "error": run_res["stderr"] or f"Search command failed with exit code {run_res['returncode']}.",
            "results": [],
        }

    stdout = run_res["stdout"]
    if manager == "dnf":
        results = _parse_dnf_search(stdout, max_results)
    elif manager == "apt":
        results = _parse_apt_search(stdout, max_results)
    elif manager == "pacman":
        results = _parse_pacman_search(stdout, max_results)
    elif manager == "zypper":
        results = _parse_zypper_search(stdout, max_results)
    elif manager == "flatpak":
        results = _parse_flatpak_search(stdout, max_results)
    elif manager == "snap":
        results = _parse_snap_find(stdout, max_results)
    else:
        results = []
        for line in stdout.splitlines()[:max_results]:
            if line.strip():
                results.append({"name": line.strip(), "summary": "", "manager": manager})

    return {
        "success": True,
        "query": query,
        "package_manager": manager,
        "count": len(results),
        "results": results,
    }


def _check_rpm_installed(package: str) -> Tuple[bool, str, str]:
    if not shutil.which("rpm"):
        return False, "", ""
    res = _run_cmd(["rpm", "-q", "--queryformat", "%{NAME}|%{VERSION}-%{RELEASE}|%{SUMMARY}\n", package])
    if res["returncode"] == 0 and res["stdout"]:
        parts = res["stdout"].splitlines()[0].split("|", 2)
        version = parts[1] if len(parts) > 1 else ""
        summary = parts[2] if len(parts) > 2 else ""
        return True, version, summary
    return False, "", ""


def _check_dpkg_installed(package: str) -> Tuple[bool, str, str]:
    if not shutil.which("dpkg-query"):
        return False, "", ""
    res = _run_cmd(["dpkg-query", "-W", "-f=${Package}|${Version}|${Status}|${binary:Summary}\n", package])
    if res["returncode"] == 0 and res["stdout"]:
        parts = res["stdout"].splitlines()[0].split("|", 3)
        status = parts[2] if len(parts) > 2 else ""
        if "installed" in status:
            version = parts[1] if len(parts) > 1 else ""
            summary = parts[3] if len(parts) > 3 else ""
            return True, version, summary
    return False, "", ""


def _check_pacman_installed(package: str) -> Tuple[bool, str, str]:
    if not shutil.which("pacman"):
        return False, "", ""
    res = _run_cmd(["pacman", "-Q", package])
    if res["returncode"] == 0 and res["stdout"]:
        parts = res["stdout"].split()
        version = parts[1] if len(parts) > 1 else ""
        return True, version, ""
    return False, "", ""


def _check_apk_installed(package: str) -> Tuple[bool, str, str]:
    if not shutil.which("apk"):
        return False, "", ""
    res = _run_cmd(["apk", "info", "-e", package])
    if res["returncode"] == 0 and res["stdout"]:
        return True, res["stdout"].strip(), ""
    return False, "", ""


def _check_flatpak_installed(package: str) -> Tuple[bool, str, str]:
    if not shutil.which("flatpak"):
        return False, "", ""
    res = _run_cmd(["flatpak", "info", package])
    if res["returncode"] == 0 and res["stdout"]:
        version = ""
        summary = ""
        for line in res["stdout"].splitlines():
            line = line.strip()
            if line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            elif " - " in line and not summary:
                summary = line.split(" - ", 1)[1].strip()
        return True, version, summary
    return False, "", ""


def _check_snap_installed(package: str) -> Tuple[bool, str, str]:
    if not shutil.which("snap"):
        return False, "", ""
    res = _run_cmd(["snap", "list", package])
    if res["returncode"] == 0 and res["stdout"]:
        lines = res["stdout"].splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            version = parts[1] if len(parts) > 1 else ""
            return True, version, ""
    return False, "", ""


def _find_packagekit_ids(
    client: PackageKitClient,
    pkg_names: List[str],
    must_be_installed: bool = False,
) -> Tuple[List[str], List[str]]:
    """Match package names to PackageKit package_ids using exact resolve with fuzzy search fallback."""
    found_ids: List[str] = []
    missing_names: List[str] = []

    for name in pkg_names:
        lowered = name.lower()
        matched_id = None

        # 1. Exact resolve
        try:
            res_resolve = client.resolve([name])
            if res_resolve.get("success") and res_resolve.get("packages"):
                candidates = res_resolve["packages"]
                if must_be_installed:
                    for c in candidates:
                        if c.get("installed"):
                            matched_id = c.get("package_id")
                            break
                else:
                    matched_id = candidates[0].get("package_id")
        except Exception:
            pass

        # 2. Search fallback (e.g. 'chrome' -> 'google-chrome-stable')
        if not matched_id:
            try:
                res_search = client.search_names(name, max_results=10)
                if res_search.get("success") and res_search.get("results"):
                    candidates = res_search["results"]
                    for c in candidates:
                        if must_be_installed and not c.get("installed"):
                            continue
                        c_name = c.get("name", "").lower()
                        if lowered in c_name or c_name in lowered:
                            matched_id = c.get("package_id")
                            break
            except Exception:
                pass

        if matched_id:
            found_ids.append(matched_id)
        else:
            missing_names.append(name)

    return found_ids, missing_names


def check_app_installed(
    package: str,
    package_manager: str = "auto",
    os_release_path: str = "/etc/os-release",
) -> Dict[str, Any]:
    """Check whether a package or application is installed on the system."""
    package = package.strip()
    if not package:
        return {"installed": False, "package": "", "error": "Package name cannot be empty."}

    if not SAFE_PKG_PATTERN.match(package):
        return {
            "installed": False,
            "package": package,
            "error": "Package name contains invalid characters.",
        }

    exec_path = shutil.which(package)
    req_manager = package_manager.strip().lower()

    # PackageKit resolve check with search fallback
    if req_manager in ("packagekit", "auto") and is_packagekit_available():
        try:
            client = PackageKitClient(timeout_seconds=10)
            res = client.resolve([package])
            installed_pkgs = [p for p in res.get("packages", []) if p.get("installed")] if res.get("success") else []
            if not installed_pkgs:
                search_res = client.search_names(package, max_results=10)
                if search_res.get("success"):
                    installed_pkgs = [
                        p for p in search_res.get("results", [])
                        if p.get("installed") and (package.lower() in p.get("name", "").lower() or p.get("name", "").lower() in package.lower())
                    ]

            if installed_pkgs:
                inst = installed_pkgs[0]
                return {
                    "installed": True,
                    "package": inst.get("name", package),
                    "version": inst.get("version", ""),
                    "manager": "packagekit",
                    "summary": inst.get("summary", ""),
                    "executable_path": exec_path,
                    "package_id": inst.get("package_id"),
                    "checked_managers": ["packagekit"],
                }
        except Exception:
            pass

    detection = detect_package_managers(os_release_path=os_release_path)
    checked_managers: List[str] = []

    if req_manager and req_manager not in ("auto", "packagekit"):
        managers_to_check = [req_manager]
    else:
        managers_to_check = []
        if detection.get("primary_native_manager"):
            managers_to_check.append(detection["primary_native_manager"])
        for mgr in detection.get("universal_managers", []):
            if mgr not in managers_to_check:
                managers_to_check.append(mgr)

    for mgr in managers_to_check:
        checked_managers.append(mgr)
        installed = False
        version = ""
        summary = ""

        if mgr in ("dnf", "zypper") or (mgr == "pacman" and shutil.which("rpm")):
            installed, version, summary = _check_rpm_installed(package)
        elif mgr == "apt":
            installed, version, summary = _check_dpkg_installed(package)
        elif mgr == "pacman":
            installed, version, summary = _check_pacman_installed(package)
        elif mgr == "apk":
            installed, version, summary = _check_apk_installed(package)
        elif mgr == "flatpak":
            installed, version, summary = _check_flatpak_installed(package)
        elif mgr == "snap":
            installed, version, summary = _check_snap_installed(package)

        if installed:
            return {
                "installed": True,
                "package": package,
                "version": version,
                "manager": mgr,
                "summary": summary,
                "executable_path": exec_path,
                "checked_managers": checked_managers,
            }

    if exec_path:
        return {
            "installed": True,
            "package": package,
            "version": "",
            "manager": "path_binary",
            "summary": "Binary exists in PATH",
            "executable_path": exec_path,
            "checked_managers": checked_managers,
        }

    return {
        "installed": False,
        "package": package,
        "version": "",
        "manager": None,
        "summary": "",
        "executable_path": None,
        "checked_managers": checked_managers,
    }


def _build_install_cmd(manager: str, packages: List[str]) -> List[str]:
    if manager == "dnf":
        return ["sudo", "-A", "dnf", "install", "-y"] + packages
    if manager == "apt":
        return ["sudo", "-A", "apt-get", "install", "-y"] + packages
    if manager == "pacman":
        return ["sudo", "-A", "pacman", "-S", "--noconfirm"] + packages
    if manager == "zypper":
        return ["sudo", "-A", "zypper", "--non-interactive", "install"] + packages
    if manager == "apk":
        return ["sudo", "-A", "apk", "add"] + packages
    if manager == "flatpak":
        return ["flatpak", "install", "-y"] + packages
    if manager == "snap":
        return ["sudo", "-A", "snap", "install"] + packages
    raise ValueError(f"Unknown package manager: {manager}")


def _build_remove_cmd(manager: str, packages: List[str], purge: bool = False) -> List[str]:
    if manager == "dnf":
        return ["sudo", "-A", "dnf", "remove", "-y"] + packages
    if manager == "apt":
        action = "purge" if purge else "remove"
        return ["sudo", "-A", "apt-get", action, "-y"] + packages
    if manager == "pacman":
        flag = "-Rns" if purge else "-R"
        return ["sudo", "-A", "pacman", flag, "--noconfirm"] + packages
    if manager == "zypper":
        return ["sudo", "-A", "zypper", "--non-interactive", "remove"] + packages
    if manager == "apk":
        return ["sudo", "-A", "apk", "del"] + packages
    if manager == "flatpak":
        cmd = ["flatpak", "uninstall", "-y"] + packages
        if purge:
            cmd.append("--delete-data")
        return cmd
    if manager == "snap":
        cmd = ["sudo", "-A", "snap", "remove"] + packages
        if purge:
            cmd.append("--purge")
        return cmd
    raise ValueError(f"Unknown package manager: {manager}")


def _format_display_command(cmd: List[str]) -> str:
    return " ".join(cmd).replace("sudo -A", "sudo")


def _prepare_cmd_env(cmd: List[str]) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    if "sudo" not in cmd:
        return os.environ.copy(), None

    askpass_path = _create_askpass_script()
    if not askpass_path:
        return None, "sudo requires an interactive password prompt, but neither kdialog nor zenity was found."

    env = os.environ.copy()
    env["SUDO_ASKPASS"] = askpass_path
    return env, None


def install_app(
    packages: Union[str, List[str]],
    package_manager: str = "auto",
    os_release_path: str = "/etc/os-release",
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Install one or more Linux packages/applications after user confirmation."""
    pkg_list = _normalize_package_list(packages)
    valid, val_err = _validate_package_names(pkg_list)
    if not valid:
        return {"success": False, "error": val_err or "Invalid package names.", "packages": pkg_list}

    req_manager = package_manager.strip().lower()

    # PackageKit direct installation path
    if req_manager == "packagekit" or (req_manager == "auto" and is_packagekit_available()):
        try:
            client = PackageKitClient(timeout_seconds=timeout_seconds)
            found_ids, missing = _find_packagekit_ids(client, pkg_list, must_be_installed=False)
            if found_ids and not missing:
                display_action = f"Install {', '.join(pkg_list)} via PackageKit (system Polkit authorization)"
                if not confirm_action(display_action):
                    return {
                        "success": False,
                        "aborted": True,
                        "message": "Installation was cancelled by the user.",
                        "packages": pkg_list,
                        "package_manager": "packagekit",
                    }
                return client.install_packages(found_ids, timeout_seconds=timeout_seconds)
            elif missing and req_manager == "auto":
                # Package wasn't found in PackageKit repositories
                return {
                    "success": False,
                    "error": f"Package(s) not found: {', '.join(missing)}. Try searching with search_packages.",
                    "packages": pkg_list,
                    "package_manager": "packagekit",
                }
        except Exception:
            pass
        if req_manager == "packagekit":
            return {"success": False, "error": f"PackageKit installation failed for: {', '.join(pkg_list)}", "packages": pkg_list}

    # Fallback to CLI manager
    manager, error = _resolve_manager(package_manager, allow_universal=True, os_release_path=os_release_path)
    if error or not manager or manager == "packagekit":
        # Resolve to native manager if packagekit was auto-selected but fell through
        detection = detect_package_managers(os_release_path=os_release_path)
        manager = detection.get("primary_native_manager")
        if not manager:
            return {"success": False, "error": error or "Package manager not found.", "packages": pkg_list}

    try:
        cmd = _build_install_cmd(manager, pkg_list)
    except Exception as exc:
        return {"success": False, "error": str(exc), "packages": pkg_list}

    display_cmd = _format_display_command(cmd)
    if not confirm_action(display_cmd):
        return {
            "success": False,
            "aborted": True,
            "message": "Installation was cancelled by the user.",
            "command": display_cmd,
            "packages": pkg_list,
        }

    env, sudo_err = _prepare_cmd_env(cmd)
    if sudo_err:
        return {"success": False, "error": sudo_err, "packages": pkg_list}

    run_res = _run_cmd(cmd, timeout_seconds=timeout_seconds, env=env)
    success = run_res["returncode"] == 0
    return {
        "success": success,
        "packages": pkg_list,
        "package_manager": manager,
        "command": display_cmd,
        "returncode": run_res["returncode"],
        "stdout": run_res["stdout"],
        "stderr": run_res["stderr"],
        "message": f"Successfully installed {', '.join(pkg_list)}" if success else f"Installation failed with exit code {run_res['returncode']}",
    }


def remove_app(
    packages: Union[str, List[str]],
    package_manager: str = "auto",
    purge: bool = False,
    os_release_path: str = "/etc/os-release",
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Remove/uninstall one or more Linux packages/applications after safety checks and user confirmation."""
    pkg_list = _normalize_package_list(packages)
    valid, val_err = _validate_package_names(pkg_list)
    if not valid:
        return {"success": False, "error": val_err or "Invalid package names.", "packages": pkg_list}

    blocked, block_err = _check_blocked_removal(pkg_list)
    if blocked:
        return {
            "success": False,
            "blocked": True,
            "error": block_err or "Removal blocked for safety.",
            "packages": pkg_list,
        }

    req_manager = package_manager.strip().lower()

    # PackageKit direct removal path
    if req_manager == "packagekit" or (req_manager == "auto" and is_packagekit_available()):
        try:
            client = PackageKitClient(timeout_seconds=timeout_seconds)
            found_ids, missing = _find_packagekit_ids(client, pkg_list, must_be_installed=True)
            if found_ids and not missing:
                display_action = f"Remove {', '.join(pkg_list)} via PackageKit (system Polkit authorization)"
                if not confirm_action(display_action):
                    return {
                        "success": False,
                        "aborted": True,
                        "message": "Package removal was cancelled by the user.",
                        "packages": pkg_list,
                        "package_manager": "packagekit",
                    }
                return client.remove_packages(found_ids, allow_deps=True, autoremove=purge, timeout_seconds=timeout_seconds)
            elif missing and req_manager == "auto":
                # If package is not installed according to PackageKit, don't blindly run sudo dnf remove!
                return {
                    "success": False,
                    "error": f"Package(s) not found or not currently installed: {', '.join(missing)}",
                    "packages": pkg_list,
                    "package_manager": "packagekit",
                }
        except Exception:
            pass
        if req_manager == "packagekit":
            return {"success": False, "error": f"PackageKit removal failed for: {', '.join(pkg_list)}", "packages": pkg_list}

    # Fallback to CLI manager
    manager, error = _resolve_manager(package_manager, allow_universal=True, os_release_path=os_release_path)
    if error or not manager or manager == "packagekit":
        detection = detect_package_managers(os_release_path=os_release_path)
        manager = detection.get("primary_native_manager")
        if not manager:
            return {"success": False, "error": error or "Package manager not found.", "packages": pkg_list}

    try:
        cmd = _build_remove_cmd(manager, pkg_list, purge=purge)
    except Exception as exc:
        return {"success": False, "error": str(exc), "packages": pkg_list}

    display_cmd = _format_display_command(cmd)
    if not confirm_action(display_cmd):
        return {
            "success": False,
            "aborted": True,
            "message": "Package removal was cancelled by the user.",
            "command": display_cmd,
            "packages": pkg_list,
        }

    env, sudo_err = _prepare_cmd_env(cmd)
    if sudo_err:
        return {"success": False, "error": sudo_err, "packages": pkg_list}

    run_res = _run_cmd(cmd, timeout_seconds=timeout_seconds, env=env)
    success = run_res["returncode"] == 0
    return {
        "success": success,
        "packages": pkg_list,
        "package_manager": manager,
        "command": display_cmd,
        "returncode": run_res["returncode"],
        "stdout": run_res["stdout"],
        "stderr": run_res["stderr"],
        "message": f"Successfully removed {', '.join(pkg_list)}" if success else f"Removal failed with exit code {run_res['returncode']}",
    }


TOOLS = [
    {
        "name": "detect_package_managers",
        "description": "Detect available Linux package managers (PackageKit D-Bus, dnf, apt, pacman, zypper, apk, flatpak, snap) and identify the primary native manager for this distribution.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "handler": detect_package_managers,
    },
    {
        "name": "search_packages",
        "description": "Search for applications or packages by name/keyword using PackageKit D-Bus or native Linux package managers without installing them.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Package name or search keyword.",
                },
                "package_manager": {
                    "type": "string",
                    "description": "Package manager to use: auto, packagekit, dnf, apt, pacman, zypper, apk, flatpak, or snap.",
                    "default": "auto",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return (1-50).",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
        "handler": search_packages,
    },
    {
        "name": "check_app_installed",
        "description": "Check whether an application or package is installed on the system, its version, and which package manager provides it.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "package": {
                    "type": "string",
                    "description": "Name of the package or application to check (e.g. 'vlc', 'git', 'python3').",
                },
                "package_manager": {
                    "type": "string",
                    "description": "Package manager to check: auto, packagekit, dnf, apt, pacman, zypper, apk, flatpak, or snap.",
                    "default": "auto",
                },
            },
            "required": ["package"],
        },
        "handler": check_app_installed,
    },
    {
        "name": "install_app",
        "description": "Install one or more Linux applications/packages using PackageKit D-Bus or native package managers (dnf, apt, pacman, zypper, apk, flatpak, snap). Requires user confirmation.",
        "risk": "admin",
        "parameters": {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of package/application names to install (e.g. ['vlc', 'htop']). Can also be a single string.",
                },
                "package_manager": {
                    "type": "string",
                    "description": "Package manager to use: auto, packagekit, dnf, apt, pacman, zypper, apk, flatpak, or snap.",
                    "default": "auto",
                },
            },
            "required": ["packages"],
        },
        "handler": install_app,
    },
    {
        "name": "remove_app",
        "description": "Remove/uninstall one or more Linux applications/packages. Protects against removing critical system packages and requires user confirmation.",
        "risk": "admin",
        "parameters": {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of package/application names to remove (e.g. ['vlc']). Can also be a single string.",
                },
                "package_manager": {
                    "type": "string",
                    "description": "Package manager to use: auto, packagekit, dnf, apt, pacman, zypper, apk, flatpak, or snap.",
                    "default": "auto",
                },
                "purge": {
                    "type": "boolean",
                    "description": "Whether to purge/delete configuration and app data (supported on apt, flatpak, snap, pacman).",
                    "default": False,
                },
            },
            "required": ["packages"],
        },
        "handler": remove_app,
    },
]
