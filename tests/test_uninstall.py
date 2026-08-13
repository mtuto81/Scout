from pathlib import Path

import uninstall


def test_source_runs_are_not_treated_as_installed(monkeypatch):
    monkeypatch.delattr(uninstall.sys, "frozen", raising=False)
    assert uninstall.installed_app_dir() is None


def test_packaged_app_dir_is_detected(monkeypatch, tmp_path):
    app_dir = tmp_path / "Scout"
    executable = app_dir / "Scout"
    monkeypatch.setattr(uninstall.sys, "frozen", True, raising=False)
    monkeypatch.setattr(uninstall.sys, "executable", str(executable))

    assert uninstall.installed_app_dir() == app_dir.resolve()


def test_uninstall_is_started_after_current_process(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(uninstall.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    app_dir = tmp_path / "Scout"
    desktop_file = tmp_path / "scout.desktop"

    uninstall.schedule_uninstall(app_dir, desktop_file)

    assert calls
    command = calls[0][0][0]
    assert command[:2] == ["sh", "-c"]
    assert command[2].startswith("set -eu")
    assert str(app_dir) in command
    assert str(desktop_file) in command
    assert calls[0][1]["start_new_session"] is True
