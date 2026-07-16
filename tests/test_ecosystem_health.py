from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from tools import ecosystem_health as health


NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def task(result: int = 0, enabled: bool = True) -> dict[str, object]:
    return {"Enabled": enabled, "LastTaskResult": result, "State": "Ready"}


def test_healthy_heartbeat_and_scheduler_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    (tmp_path / "h.json").write_text('{"status":"SUCCEEDED","finished_at_utc":"2026-07-15T00:00:00Z"}', encoding="utf-8")
    item = health.assess_task("x", "p", True, 36, task(), health.load_heartbeat(tmp_path / "h.json"), NOW)
    assert item["status"] == "SUCCEEDED"


def test_nonzero_scheduler_result_wins_over_heartbeat(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    heartbeat = {"status": "SUCCEEDED", "finished_at_utc": "2026-07-15T00:00:00Z"}
    assert health.assess_task("x", "p", True, 36, task(1), heartbeat, NOW)["status"] == "FAILED"


def test_stale_heartbeat_is_detected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    heartbeat = {"status": "SUCCEEDED", "finished_at_utc": "2026-07-10T00:00:00Z"}
    assert health.assess_task("x", "p", True, 36, task(), heartbeat, NOW)["status"] == "STALE"


def test_missing_heartbeat_is_unknown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    assert health.assess_task("x", "p", True, 36, task(), None, NOW)["status"] == "UNKNOWN"


def test_expected_disabled_legacy_task_is_skipped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    assert health.assess_task("x", "p", False, 36, task(enabled=False), None, NOW)["status"] == "SKIPPED"


def test_report_exit_code_prioritizes_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    monkeypatch.setattr(health, "TASKS", (("x", "p", True, 36),))
    report = health.health_report(provider=lambda _: task(42), now=NOW)
    assert report["overall_status"] == "FAILED" and report["exit_code"] == 1


def test_json_serialization_is_deterministic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    monkeypatch.setattr(health, "TASKS", (("x", "p", False, 36),))
    first = health.health_report(provider=lambda _: task(enabled=False), now=NOW)
    second = health.health_report(provider=lambda _: task(enabled=False), now=NOW)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_invalid_scheduler_result_is_unknown_instead_of_crashing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(health, "heartbeat_path", lambda *_: tmp_path / "h.json")
    invalid = {"Enabled": True, "LastTaskResult": "not-a-number"}
    item = health.assess_task("x", "p", True, 36, invalid, None, NOW)
    assert item["status"] == "UNKNOWN"


def test_load_tasks_validates_declarative_configuration(tmp_path: Path) -> None:
    source = tmp_path / "tasks.json"
    source.write_text('[{"task_name":"x","project":"workspace","expected_enabled":true,"max_age_hours":24}]', encoding="utf-8")
    assert health.load_tasks(source) == (("x", "workspace", True, 24),)
    source.write_text('{"task_name":"x"}', encoding="utf-8")
    try:
        health.load_tasks(source)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid task configuration must fail closed")


def test_query_task_and_main_use_declarative_configuration(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "tasks.json"
    source.write_text('[{"task_name":"x","project":"workspace","expected_enabled":false,"max_age_hours":24}]', encoding="utf-8")
    monkeypatch.setattr(health.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout='{"TaskName":"x"}'))
    assert health.query_task("x") == {"TaskName": "x"}
    monkeypatch.setattr(health, "health_report", lambda **_: {"overall_status": "HEALTHY", "exit_code": 0, "automations": []})
    assert health.main(["--json", "--tasks-file", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["overall_status"] == "HEALTHY"
