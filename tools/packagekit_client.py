"""PackageKit D-Bus client for direct Linux package operations without CLI subprocesses.

Communicates with org.freedesktop.PackageKit over the system D-Bus.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple


def _unwrap(val: Any) -> Any:
    """Helper to unwrap GLib.Variant or return value as-is."""
    if hasattr(val, "unpack"):
        return val.unpack()
    if hasattr(val, "get_string"):
        return val.get_string()
    return val


def parse_package_id(package_id: str) -> Dict[str, str]:
    """Parse a PackageKit package_id string (name;version;arch;data)."""
    parts = package_id.split(";")
    return {
        "name": parts[0] if len(parts) > 0 else package_id,
        "version": parts[1] if len(parts) > 1 else "",
        "arch": parts[2] if len(parts) > 2 else "",
        "data": parts[3] if len(parts) > 3 else "",
        "package_id": package_id,
    }


def is_packagekit_available() -> bool:
    """Check if the PackageKit system D-Bus daemon is reachable."""
    try:
        from dasbus.connection import SystemMessageBus
        bus = SystemMessageBus()
        pk = bus.get_proxy("org.freedesktop.PackageKit", "/org/freedesktop/PackageKit")
        # Probe by checking if we can create a transaction or read a property
        tid = pk.CreateTransaction()
        return bool(tid)
    except Exception:
        return False


class PackageKitClient:
    """High-level client for PackageKit D-Bus transactions."""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def _get_bus(self):
        from dasbus.connection import SystemMessageBus
        return SystemMessageBus()

    def _create_transaction(self, bus):
        pk = bus.get_proxy("org.freedesktop.PackageKit", "/org/freedesktop/PackageKit")
        tid_path = pk.CreateTransaction()
        trans = bus.get_proxy("org.freedesktop.PackageKit", tid_path)
        return tid_path, trans

    def _run_transaction(
        self,
        action_name: str,
        setup_callbacks: Callable[[Any, Any, Dict[str, Any]], None],
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generic transaction runner using dasbus EventLoop and GLib timeout."""
        from dasbus.loop import EventLoop
        from gi.repository import GLib

        timeout = timeout_seconds or self.timeout_seconds
        bus = self._get_bus()
        tid_path, trans = self._create_transaction(bus)
        loop = EventLoop()

        context: Dict[str, Any] = {
            "status": None,
            "runtime": None,
            "error_code": None,
            "error_details": None,
            "timed_out": False,
            "finished": False,
        }

        def on_timeout():
            if not context["finished"]:
                context["timed_out"] = True
                loop.quit()
            return False

        timeout_id = GLib.timeout_add_seconds(timeout, on_timeout)

        def on_finished(status, runtime):
            context["finished"] = True
            context["status"] = int(status)
            context["runtime"] = int(runtime)
            GLib.source_remove(timeout_id)
            loop.quit()

        def on_error(code, details):
            context["error_code"] = int(code)
            context["error_details"] = str(details)

        trans.Finished.connect(on_finished)
        trans.ErrorCode.connect(on_error)

        setup_callbacks(trans, loop, context)

        loop.run()
        return context

    def search_names(self, query: str, max_results: int = 25) -> Dict[str, Any]:
        """Search packages by name/keyword over PackageKit D-Bus."""
        packages: List[Dict[str, Any]] = []

        def setup(trans, loop, context):
            def on_package(info, pkg_id, summary):
                if len(packages) < max_results:
                    parsed = parse_package_id(str(pkg_id))
                    is_installed = int(info) == 1
                    packages.append({
                        "name": parsed["name"],
                        "version": parsed["version"],
                        "arch": parsed["arch"],
                        "repo": parsed["data"],
                        "summary": str(summary).strip(),
                        "installed": is_installed,
                        "package_id": str(pkg_id),
                        "manager": "packagekit",
                    })

            trans.Package.connect(on_package)
            # Filter 0 = FILTER_NONE
            trans.SearchNames(0, [query])

        ctx = self._run_transaction("SearchNames", setup)

        if ctx["timed_out"]:
            return {
                "success": False,
                "error": f"PackageKit search timed out after {self.timeout_seconds}s.",
                "results": packages,
            }

        if ctx["error_details"]:
            return {
                "success": False,
                "error": ctx["error_details"],
                "results": packages,
            }

        return {
            "success": True,
            "query": query,
            "package_manager": "packagekit",
            "count": len(packages),
            "results": packages,
        }

    def resolve(self, package_names: List[str]) -> Dict[str, Any]:
        """Resolve package names to exact PackageKit IDs and install status."""
        packages: List[Dict[str, Any]] = []

        def setup(trans, loop, context):
            def on_package(info, pkg_id, summary):
                parsed = parse_package_id(str(pkg_id))
                is_installed = int(info) == 1
                packages.append({
                    "name": parsed["name"],
                    "version": parsed["version"],
                    "arch": parsed["arch"],
                    "repo": parsed["data"],
                    "summary": str(summary).strip(),
                    "installed": is_installed,
                    "package_id": str(pkg_id),
                    "manager": "packagekit",
                })

            trans.Package.connect(on_package)
            trans.Resolve(0, package_names)

        ctx = self._run_transaction("Resolve", setup)

        if ctx["timed_out"]:
            return {"success": False, "error": "PackageKit resolve timed out.", "packages": packages}

        if ctx["error_details"]:
            return {"success": False, "error": ctx["error_details"], "packages": packages}

        return {"success": True, "packages": packages}

    def get_details(self, package_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Retrieve detailed description, license, size, and URL for package IDs."""
        details_map: Dict[str, Dict[str, Any]] = {}

        def setup(trans, loop, context):
            def on_details(*args):
                if not args:
                    return
                # PackageKit 2.0+ passes a single dict with GLib.Variant values
                if len(args) == 1 and isinstance(args[0], dict):
                    raw = args[0]
                    pkg_id = str(_unwrap(raw.get("package-id", "")))
                    details_map[pkg_id] = {
                        "package_id": pkg_id,
                        "summary": str(_unwrap(raw.get("summary", ""))),
                        "description": str(_unwrap(raw.get("description", ""))),
                        "license": str(_unwrap(raw.get("license", ""))),
                        "url": str(_unwrap(raw.get("url", ""))),
                        "size": int(_unwrap(raw.get("size", 0)) or 0),
                        "download_size": int(_unwrap(raw.get("download-size", 0)) or 0),
                    }
                # Legacy PackageKit passes positional arguments
                elif len(args) >= 6:
                    pkg_id = str(args[0])
                    details_map[pkg_id] = {
                        "package_id": pkg_id,
                        "license": str(args[1]),
                        "group": str(args[2]),
                        "description": str(args[3]),
                        "url": str(args[4]),
                        "size": int(args[5]) if isinstance(args[5], (int, float)) else 0,
                    }

            trans.Details.connect(on_details)
            trans.GetDetails(package_ids)

        self._run_transaction("GetDetails", setup)
        return details_map

    def install_packages(self, package_ids: List[str], timeout_seconds: int = 300) -> Dict[str, Any]:
        """Install packages using PackageKit with native desktop Polkit authorization."""
        def setup(trans, loop, context):
            # TransactionFlags: 0 (default)
            trans.InstallPackages(0, package_ids)

        ctx = self._run_transaction("InstallPackages", setup, timeout_seconds=timeout_seconds)

        if ctx["timed_out"]:
            return {
                "success": False,
                "error": f"PackageKit install timed out after {timeout_seconds}s.",
                "package_ids": package_ids,
            }

        if ctx["error_details"]:
            return {
                "success": False,
                "error": ctx["error_details"],
                "package_ids": package_ids,
            }

        # Status: 1 indicates EXIT_SUCCESS in PackageKit
        success = ctx.get("status") == 1
        return {
            "success": success,
            "status": ctx.get("status"),
            "package_ids": package_ids,
            "message": f"Successfully installed {len(package_ids)} package(s) via PackageKit." if success else "PackageKit installation ended without success code.",
        }

    def remove_packages(
        self,
        package_ids: List[str],
        allow_deps: bool = True,
        autoremove: bool = False,
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Remove/uninstall packages using PackageKit with native desktop Polkit authorization."""
        def setup(trans, loop, context):
            # TransactionFlags: 0
            trans.RemovePackages(0, package_ids, allow_deps, autoremove)

        ctx = self._run_transaction("RemovePackages", setup, timeout_seconds=timeout_seconds)

        if ctx["timed_out"]:
            return {
                "success": False,
                "error": f"PackageKit remove timed out after {timeout_seconds}s.",
                "package_ids": package_ids,
            }

        if ctx["error_details"]:
            return {
                "success": False,
                "error": ctx["error_details"],
                "package_ids": package_ids,
            }

        success = ctx.get("status") == 1
        return {
            "success": success,
            "status": ctx.get("status"),
            "package_ids": package_ids,
            "message": f"Successfully removed {len(package_ids)} package(s) via PackageKit." if success else "PackageKit removal ended without success code.",
        }
