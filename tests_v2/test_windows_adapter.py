import json
import subprocess
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from predictor_ops import windows
from predictor_ops.models import OperationalState


def _result(payload=None, returncode=0):
    return SimpleNamespace(
        stdout=json.dumps(payload) if payload is not None else "", stderr="denied", returncode=returncode
    )


def test_non_windows_fails_closed(monkeypatch):
    monkeypatch.setattr(windows.os, "name", "posix")
    result = windows.inspect_scheduled_task("anything")
    assert result.status is OperationalState.CONFIGURATION_ERROR and result.task is None


def test_present_disabled_failed_never_run_and_success(monkeypatch):
    monkeypatch.setattr(windows.os, "name", "nt")
    values = [
        ({"enabled": False}, OperationalState.SKIPPED),
        ({"enabled": True, "last_result": 9, "last_run": "2026-01-01T00:00:00Z"}, OperationalState.FAILED),
        ({"enabled": True, "last_result": 0, "last_run": "0001-01-01T00:00:00Z"}, OperationalState.WAITING),
        ({"enabled": True, "last_result": 0, "last_run": "2026-01-01T00:00:00Z"}, OperationalState.SUCCEEDED),
    ]
    for payload, expected in values:
        monkeypatch.setattr(windows.subprocess, "run", lambda *a, payload=payload, **k: _result(payload))
        assert windows.inspect_scheduled_task("task").status is expected


def test_quoting_spaced_paths_no_console_and_compat_view(monkeypatch):
    monkeypatch.setattr(windows.os, "name", "nt")
    captured = {}
    payload = {
        "enabled": True,
        "last_result": 0,
        "last_run": "2026-01-01T00:00:00Z",
        "actions": [{"execute": "C:\\Program Files\\Python\\python.exe"}],
    }

    def fake_run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return _result(payload)

    monkeypatch.setattr(windows.subprocess, "run", fake_run)
    assert windows.query_scheduled_task("owner's task") == payload
    script = captured["command"][-1]
    assert "'owner''s task'" in script
    assert captured["kwargs"]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_permission_missing_powershell_invalid_json_and_schema_fail_closed(monkeypatch):
    monkeypatch.setattr(windows.os, "name", "nt")
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: _result(returncode=5))
    assert windows.inspect_scheduled_task("x").status is OperationalState.CONFIGURATION_ERROR
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert windows.inspect_scheduled_task("x").status is OperationalState.CONFIGURATION_ERROR
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="not-json", returncode=0))
    assert windows.inspect_scheduled_task("x").status is OperationalState.CONFIGURATION_ERROR
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: _result({"enabled": "yes"}))
    assert windows.inspect_scheduled_task("x").status is OperationalState.CONFIGURATION_ERROR


def test_overdue_is_fail_closed():
    now = datetime(2026, 1, 2, tzinfo=UTC)
    assert windows.is_overdue({}, now=now)
    assert windows.is_overdue({"next_run": "invalid"}, now=now)
    assert windows.is_overdue({"next_run": (now - timedelta(seconds=1)).isoformat()}, now=now)
    assert not windows.is_overdue({"next_run": (now + timedelta(seconds=1)).isoformat()}, now=now)
