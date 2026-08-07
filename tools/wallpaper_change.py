import json
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".svg", ".tiff", ".tif"}

WALLPAPER_DIRS = [
    os.path.expanduser("~/Pictures/Wallpapers"),
    os.path.expanduser("~/.local/share/wallpapers"),
    "/usr/share/wallpapers",
    "/usr/share/backgrounds",
]


def _run(command: List[str], timeout_seconds: int = 10) -> Dict[str, Any]:
    executable = shutil.which(command[0])
    if not executable:
        return {
            "ok": False,
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
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Timed out after {timeout_seconds}s", "returncode": None}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": None}


def _detect_desktop_env() -> Dict[str, Any]:
    xdg = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session = os.environ.get("DESKTOP_SESSION", "")
    desktop = os.environ.get("GDMSESSION", "")

    combined = f"{xdg} {session} {desktop}".lower()

    if "plasma" in combined or "kde" in combined:
        version = _detect_kde_version()
        return {"name": "KDE Plasma", "version": version, "variant": f"plasma{version}"}
    if "gnome" in combined or "unity" in combined or "budgie" in combined:
        return {"name": "GNOME", "version": "", "variant": "gnome"}
    if "cinnamon" in combined:
        return {"name": "Cinnamon", "version": "", "variant": "cinnamon"}
    if "mate" in combined:
        return {"name": "MATE", "version": "", "variant": "mate"}
    if "xfce" in combined:
        return {"name": "XFCE", "version": "", "variant": "xfce"}
    if "hyprland" in combined:
        return {"name": "Hyprland", "version": "", "variant": "hyprland"}
    if "sway" in combined:
        return {"name": "Sway", "version": "", "variant": "sway"}

    if shutil.which("plasma-apply-wallpaperimage"):
        return {"name": "KDE Plasma", "version": "6", "variant": "plasma6"}
    if shutil.which("gsettings"):
        return {"name": "GNOME", "version": "", "variant": "gnome"}
    if shutil.which("xfconf-query"):
        return {"name": "XFCE", "version": "", "variant": "xfce"}

    return {"name": "Unknown", "version": "", "variant": "unknown"}


def _detect_kde_version() -> str:
    r = _run(["plasma-apply-wallpaperimage", "--help"], timeout_seconds=5)
    if r["ok"] or "plasma-apply-wallpaperimage" in r.get("stderr", ""):
        return "6"
    r2 = _run(["qdbus", "--version"], timeout_seconds=5)
    if r2["ok"]:
        return "5"
    return "6"


def _is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMAGE_EXTENSIONS


def _resolve_image_path(image: str) -> Optional[str]:
    if os.path.isfile(image) and _is_image_file(image):
        return os.path.abspath(image)
    return None


def _download_image(url: str) -> Optional[str]:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None

        req = urllib.request.Request(url, headers={"User-Agent": "Scout/0.1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()

        if "image" not in content_type and not any(
            url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS
        ):
            return None

        content_type_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/svg+xml": ".svg",
        }
        ext = content_type_map.get(content_type.split(";")[0].strip(), "")
        if not ext:
            ext = os.path.splitext(parsed.path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".jpg"

        wallpaper_dir = os.path.expanduser("~/.local/share/scout/wallpapers")
        os.makedirs(wallpaper_dir, exist_ok=True)

        filename = f"wallpaper_{abs(hash(url))}{ext}"
        filepath = os.path.join(wallpaper_dir, filename)

        with open(filepath, "wb") as f:
            f.write(data)

        return filepath
    except Exception:
        return None


def _get_wallpaper_kde5(monitor: Optional[str] = None) -> Optional[str]:
    script = (
        "var allDesktops = desktops();"
        "for (var i = 0; i < allDesktops.length; i++) {"
        "    var d = allDesktops[i];"
        "    if (d.wallpaperPlugin) {"
        "        print(d.currentConfigGroup.toString());"
        "        print(JSON.stringify(d.wallpaperPlugin));"
        "        print(d.readConfig('Image'));"
        "    }"
        "}"
    )
    r = _run(["qdbus", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script])
    if r["ok"] and r["stdout"]:
        for line in r["stdout"].splitlines():
            if line.startswith("file://"):
                return _strip_file_uri(line)
        for line in r["stdout"].splitlines():
            if "/wallpapers/" in line or "/backgrounds/" in line:
                return _strip_file_uri(line)
    return None


def _strip_file_uri(path: str) -> str:
    if path.startswith("file://"):
        return path[7:]
    return path


def _get_wallpaper_kde6(monitor: Optional[str] = None) -> Optional[str]:
    r = _run(["plasma-apply-wallpaperimage", "--current-wallpaper"], timeout_seconds=5)
    if r["ok"] and r["stdout"]:
        return _strip_file_uri(r["stdout"])

    config_path = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "Image=" in line:
                        value = line.split("=", 1)[1].strip()
                        if value:
                            return value
        except Exception:
            pass
    return None


def _set_wallpaper_kde5(image_path: str, monitor: Optional[str] = None) -> bool:
    escaped = image_path.replace("\\", "\\\\").replace("'", "\\'")
    uri = "file://" + escaped
    script = (
        "var allDesktops = desktops();"
        "for (var i = 0; i < allDesktops.length; i++) {"
        "    var d = allDesktops[i];"
        "    d.wallpaperPlugin = 'org.kde.image';"
        "    d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];"
        "    d.writeConfig('Image', '" + uri + "');"
        "}"
    )
    r = _run(["qdbus", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script])
    return r["ok"]


def _set_wallpaper_kde6(image_path: str, monitor: Optional[str] = None) -> bool:
    cmd = ["plasma-apply-wallpaperimage", image_path]
    if monitor:
        cmd.extend(["--screen", monitor])
    r = _run(cmd)
    if r["ok"]:
        return True
    if r["ok"] is False and "plasma-apply-wallpaperimage" in r.get("stderr", ""):
        return _set_wallpaper_kde5(image_path, monitor)
    return False


def _set_wallpaper_gnome(image_path: str, monitor: Optional[str] = None) -> bool:
    uri = f"file://{image_path}"
    r1 = _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
    r2 = _run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])
    return r1["ok"] or r2["ok"]


def _get_wallpaper_gnome(monitor: Optional[str] = None) -> Optional[str]:
    r = _run(["gsettings", "get", "org.gnome.desktop.background", "picture-uri"])
    if r["ok"] and r["stdout"]:
        value = r["stdout"].strip().strip("'")
        if value.startswith("file://"):
            return value[7:]
        return value
    return None


def _set_wallpaper_cinnamon(image_path: str, monitor: Optional[str] = None) -> bool:
    uri = f"file://{image_path}"
    r1 = _run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri])
    r2 = _run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri-dark", uri])
    return r1["ok"] or r2["ok"]


def _get_wallpaper_cinnamon(monitor: Optional[str] = None) -> Optional[str]:
    r = _run(["gsettings", "get", "org.cinnamon.desktop.background", "picture-uri"])
    if r["ok"] and r["stdout"]:
        value = r["stdout"].strip().strip("'")
        if value.startswith("file://"):
            return value[7:]
        return value
    return None


def _set_wallpaper_mate(image_path: str, monitor: Optional[str] = None) -> bool:
    r = _run(["gsettings", "set", "org.mate.background", "picture-filename", image_path])
    return r["ok"]


def _get_wallpaper_mate(monitor: Optional[str] = None) -> Optional[str]:
    r = _run(["gsettings", "get", "org.mate.background", "picture-filename"])
    if r["ok"] and r["stdout"]:
        return r["stdout"].strip().strip("'")
    return None


def _set_wallpaper_xfce(image_path: str, monitor: Optional[str] = None) -> bool:
    props = [
        "/backdrop/screen0/monitor0/workspace0/last-image",
        "/backdrop/screen0/monitorHDMI-1/workspace0/last-image",
        "/backdrop/screen0/monitorDP-1/workspace0/last-image",
    ]
    ok = False
    for prop in props:
        r = _run(["xfconf-query", "-c", "xfce4-desktop", "-p", prop, "-s", image_path])
        if r["ok"]:
            ok = True
    return ok


def _get_wallpaper_xfce(monitor: Optional[str] = None) -> Optional[str]:
    props = [
        "/backdrop/screen0/monitor0/workspace0/last-image",
        "/backdrop/screen0/monitorHDMI-1/workspace0/last-image",
    ]
    for prop in props:
        r = _run(["xfconf-query", "-c", "xfce4-desktop", "-p", prop])
        if r["ok"] and r["stdout"]:
            value = r["stdout"].strip()
            if os.path.isfile(value):
                return value
    return None


def _set_wallpaper_hyprland(image_path: str, monitor: Optional[str] = None) -> bool:
    r1 = _run(["hyprctl", "hyprpaper", "preload", image_path])
    wallpaper_str = f",{image_path}" if not monitor else f"{monitor},{image_path}"
    r2 = _run(["hyprctl", "hyprpaper", "wallpaper", wallpaper_str])
    return r1["ok"] and r2["ok"]


_SETTERS = {
    "plasma5": _set_wallpaper_kde5,
    "plasma6": _set_wallpaper_kde6,
    "gnome": _set_wallpaper_gnome,
    "cinnamon": _set_wallpaper_cinnamon,
    "mate": _set_wallpaper_mate,
    "xfce": _set_wallpaper_xfce,
    "hyprland": _set_wallpaper_hyprland,
}

_GETTERS = {
    "plasma5": _get_wallpaper_kde5,
    "plasma6": _get_wallpaper_kde6,
    "gnome": _get_wallpaper_gnome,
    "cinnamon": _get_wallpaper_cinnamon,
    "mate": _get_wallpaper_mate,
    "xfce": _get_wallpaper_xfce,
}


def set_wallpaper(image: str, monitor: Optional[str] = None) -> Dict[str, Any]:
    if image.startswith(("http://", "https://")):
        local_path = _download_image(image)
        if not local_path:
            return {"success": False, "error": "Failed to download image from URL."}
        image_path = local_path
        source = "downloaded"
    else:
        resolved = _resolve_image_path(image)
        if not resolved:
            return {"success": False, "error": f"Image file not found or unsupported format: {image}"}
        image_path = resolved
        source = "local"

    de = _detect_desktop_env()
    variant = de["variant"]
    setter = _SETTERS.get(variant)
    if not setter:
        return {
            "success": False,
            "error": f"Unsupported desktop environment: {de['name']}.",
            "detected_de": de,
        }

    ok = setter(image_path, monitor)
    if ok:
        return {
            "success": True,
            "wallpaper": image_path,
            "source": source,
            "desktop_environment": de["name"],
        }
    return {"success": False, "error": "Wallpaper setter command failed.", "desktop_environment": de["name"]}


def get_wallpaper(monitor: Optional[str] = None) -> Dict[str, Any]:
    de = _detect_desktop_env()
    variant = de["variant"]
    getter = _GETTERS.get(variant)
    if not getter:
        return {"wallpaper": None, "error": f"Unsupported desktop environment: {de['name']}"}

    path = getter(monitor)
    if path:
        path = _strip_file_uri(path)
    exists = os.path.exists(path) if path else False
    return {
        "wallpaper": path,
        "file_exists": exists,
        "desktop_environment": de["name"],
    }


def list_wallpapers(directory: Optional[str] = None) -> Dict[str, Any]:
    dirs_to_scan = [directory] if directory else WALLPAPER_DIRS
    results: Dict[str, List[str]] = {}

    for d in dirs_to_scan:
        d = os.path.expanduser(d)
        if not os.path.isdir(d):
            continue
        images = []
        try:
            for root, _subdirs, files in os.walk(d):
                depth = root[len(d):].count(os.sep)
                if depth > 3:
                    continue
                for entry in sorted(files):
                    full = os.path.join(root, entry)
                    if _is_image_file(entry):
                        images.append(full)
        except PermissionError:
            continue
        if images:
            results[d] = images

    total = sum(len(v) for v in results.values())
    return {"directories": results, "total_count": total}


def get_desktop_env() -> Dict[str, Any]:
    de = _detect_desktop_env()
    return {
        "name": de["name"],
        "version": de["version"],
        "variant": de["variant"],
        "can_set_wallpaper": de["variant"] in _SETTERS,
        "can_get_wallpaper": de["variant"] in _GETTERS,
        "xdg_current_desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "desktop_session": os.environ.get("DESKTOP_SESSION", ""),
    }


TOOLS = [
    {
        "name": "set_wallpaper",
        "description": "Change the desktop wallpaper. Accepts a local file path or an HTTP/HTTPS URL. The image is downloaded and applied automatically when a URL is provided.",
        "risk": "medium",
        "parameters": {
            "type": "object",
            "properties": {
                "image": {
                    "type": "string",
                    "description": "Path to an image file or an HTTP/HTTPS URL to download.",
                },
                "monitor": {
                    "type": "string",
                    "description": "Optional monitor name for multi-monitor setups.",
                },
            },
            "required": ["image"],
        },
        "handler": set_wallpaper,
    },
    {
        "name": "get_wallpaper",
        "description": "Get the current desktop wallpaper path.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "monitor": {
                    "type": "string",
                    "description": "Optional monitor name for multi-monitor setups.",
                },
            },
        },
        "handler": get_wallpaper,
    },
    {
        "name": "list_wallpapers",
        "description": "List available wallpaper image files from common system and user directories.",
        "risk": "read_only",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Optional directory to scan. Defaults to common wallpaper locations.",
                },
            },
        },
        "handler": list_wallpapers,
    },
    {
        "name": "get_desktop_env",
        "description": "Detect the current Linux desktop environment and whether wallpaper tools are available.",
        "risk": "read_only",
        "parameters": {"type": "object", "properties": {}},
        "handler": get_desktop_env,
    },
]
