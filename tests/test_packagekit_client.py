import pytest
from unittest.mock import patch, MagicMock
import dasbus.connection

from tools.packagekit_client import (
    PackageKitClient,
    parse_package_id,
    is_packagekit_available,
    _unwrap,
)


class TestPackageKitHelpers:
    def test_parse_package_id(self):
        pid = "vlc;1:3.0.23-10.fc44;x86_64;installed"
        parsed = parse_package_id(pid)
        assert parsed["name"] == "vlc"
        assert parsed["version"] == "1:3.0.23-10.fc44"
        assert parsed["arch"] == "x86_64"
        assert parsed["data"] == "installed"
        assert parsed["package_id"] == pid

    def test_parse_package_id_simple(self):
        parsed = parse_package_id("htop")
        assert parsed["name"] == "htop"
        assert parsed["version"] == ""
        assert parsed["arch"] == ""

    def test_unwrap_variant(self):
        class MockVariant:
            def unpack(self):
                return "unpacked_value"

        assert _unwrap(MockVariant()) == "unpacked_value"
        assert _unwrap("plain_string") == "plain_string"
        assert _unwrap(123) == 123


class TestPackageKitAvailability:
    def test_available_when_transaction_created(self):
        mock_bus = MagicMock()
        mock_pk = MagicMock()
        mock_pk.CreateTransaction.return_value = "/transaction/123"
        mock_bus.get_proxy.return_value = mock_pk

        with patch("dasbus.connection.SystemMessageBus", return_value=mock_bus):
            assert is_packagekit_available() is True

    def test_unavailable_when_exception_raised(self):
        with patch("dasbus.connection.SystemMessageBus", side_effect=Exception("D-Bus unreachable")):
            assert is_packagekit_available() is False


class TestPackageKitClientOperations:
    def test_search_names_success(self):
        client = PackageKitClient()

        def fake_run(action, setup, timeout_seconds=None):
            mock_trans = MagicMock()
            mock_loop = MagicMock()
            context = {"finished": True, "status": 1, "error_details": None, "timed_out": False}
            setup(mock_trans, mock_loop, context)

            # Trigger the Package callback registered on trans.Package
            pkg_cb = mock_trans.Package.connect.call_args[0][0]
            pkg_cb(1, "vlc;3.0.20;x86_64;installed", "VLC media player")
            pkg_cb(2, "vlc-core;3.0.20;x86_64;updates", "VLC core")
            return context

        with patch.object(client, "_run_transaction", side_effect=fake_run):
            res = client.search_names("vlc", max_results=5)
            assert res["success"] is True
            assert res["count"] == 2
            assert res["results"][0]["name"] == "vlc"
            assert res["results"][0]["installed"] is True
            assert res["results"][1]["name"] == "vlc-core"
            assert res["results"][1]["installed"] is False

    def test_search_names_timeout(self):
        client = PackageKitClient(timeout_seconds=5)

        def fake_run(action, setup, timeout_seconds=None):
            return {"finished": False, "status": None, "error_details": None, "timed_out": True}

        with patch.object(client, "_run_transaction", side_effect=fake_run):
            res = client.search_names("slow_query")
            assert res["success"] is False
            assert "timed out" in res["error"]

    def test_resolve_packages(self):
        client = PackageKitClient()

        def fake_run(action, setup, timeout_seconds=None):
            mock_trans = MagicMock()
            mock_loop = MagicMock()
            context = {"finished": True, "status": 1, "error_details": None, "timed_out": False}
            setup(mock_trans, mock_loop, context)

            pkg_cb = mock_trans.Package.connect.call_args[0][0]
            pkg_cb(1, "python3;3.14.7-1.fc44;x86_64;installed", "Python interpreter")
            return context

        with patch.object(client, "_run_transaction", side_effect=fake_run):
            res = client.resolve(["python3"])
            assert res["success"] is True
            assert len(res["packages"]) == 1
            assert res["packages"][0]["name"] == "python3"
            assert res["packages"][0]["installed"] is True

    def test_get_details(self):
        client = PackageKitClient()

        def fake_run(action, setup, timeout_seconds=None):
            mock_trans = MagicMock()
            mock_loop = MagicMock()
            context = {"finished": True, "status": 1, "error_details": None, "timed_out": False}
            setup(mock_trans, mock_loop, context)

            details_cb = mock_trans.Details.connect.call_args[0][0]
            details_cb({
                "package-id": "vlc;3.0.20;x86_64;updates",
                "summary": "VLC media player",
                "description": "Full description of VLC",
                "license": "GPLv2+",
                "url": "https://videolan.org",
                "size": 5000000,
            })
            return context

        with patch.object(client, "_run_transaction", side_effect=fake_run):
            details = client.get_details(["vlc;3.0.20;x86_64;updates"])
            pkg = details.get("vlc;3.0.20;x86_64;updates")
            assert pkg is not None
            assert pkg["license"] == "GPLv2+"
            assert pkg["url"] == "https://videolan.org"
            assert pkg["description"] == "Full description of VLC"

    def test_install_packages_success(self):
        client = PackageKitClient()

        def fake_run(action, setup, timeout_seconds=None):
            mock_trans = MagicMock()
            mock_loop = MagicMock()
            context = {"finished": True, "status": 1, "error_details": None, "timed_out": False}
            setup(mock_trans, mock_loop, context)
            return context

        with patch.object(client, "_run_transaction", side_effect=fake_run):
            res = client.install_packages(["vlc;3.0.20;x86_64;updates"])
            assert res["success"] is True
            assert "Successfully installed" in res["message"]

    def test_remove_packages_success(self):
        client = PackageKitClient()

        def fake_run(action, setup, timeout_seconds=None):
            mock_trans = MagicMock()
            mock_loop = MagicMock()
            context = {"finished": True, "status": 1, "error_details": None, "timed_out": False}
            setup(mock_trans, mock_loop, context)
            return context

        with patch.object(client, "_run_transaction", side_effect=fake_run):
            res = client.remove_packages(["vlc;3.0.20;x86_64;installed"])
            assert res["success"] is True
            assert "Successfully removed" in res["message"]
