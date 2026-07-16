"""Read-only health check for the known operational automations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent

TASKS = (
    ("GarimpoFase1", "previsao-cripto", True, 36),
    ("GarimpoV3Daily", "previsao-cripto", True, 36),
    ("cripto-watchdog-coleta", "previsao-cripto", True, 36),
    ("brasileirao-sombra-manha", "brasileirao-predictor", True, 36),
    ("brasileirao-sombra-noite", "brasileirao-predictor", True, 36),
    ("cs-ratings-semanal", "cs-predictor", True, 216),
    ("lol-ratings-semanal", "lol-predictor", True, 216),
    ("ecosystem-health-semanal", "workspace", True, 216),
    ("GarimpoInvestimentos-ColetaDiaria", "previsao-cripto", False, 36),
)


def heartbeat_path(task_name: str, project: str) -> Path:
    if project == "workspace":
        return ROOT / "logs" / "operations" / f"{task_name}.heartbeat.json"
    return ROOT / project / "logs" / "operations" / f"{task_name}.heartbeat.json"


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def query_task(task_name: str) -> dict[str, Any] | None:
    quoted = _powershell_quote(task_name)
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$t=Get-ScheduledTask -TaskName {quoted}; $i=Get-ScheduledTaskInfo -TaskName {quoted}; "
        "[pscustomobject]@{TaskName=$t.TaskName;State=[string]$t.State;Enabled=[bool]$t.Settings.Enabled;"
        "LastRunTime=$i.LastRunTime.ToUniversalTime().ToString('o');NextRunTime=$i.NextRunTime.ToUniversalTime().ToString('o');"
        "LastTaskResult=[int64]$i.LastTaskResult;Action=($t.Actions|ForEach-Object {$_.Execute+' '+$_.Arguments}) -join ';';"
        "WorkingDirectory=($t.Actions|ForEach-Object {$_.WorkingDirectory}) -join ';';"
        "MultipleInstances=[string]$t.Settings.MultipleInstances;StartWhenAvailable=[bool]$t.Settings.StartWhenAvailable} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0:
        return None
    value = json.loads(result.stdout)
    return value if isinstance(value, dict) else None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def assess_task(task_name: str, project: str, expected_enabled: bool, max_age_hours: int, task: dict[str, Any] | None, heartbeat: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    item: dict[str, Any] = {"task_name": task_name, "project": project, "expected_enabled": expected_enabled, "heartbeat_path": str(heartbeat_path(task_name, project))}
    if task is None:
        item.update(status="UNKNOWN", reason="Task Scheduler task not queryable")
        return item
    item["scheduler"] = task
    if not expected_enabled:
        item.update(status="SKIPPED" if not task.get("Enabled", False) else "PARTIAL", reason="legacy task is intentionally disabled")
        return item
    if not task.get("Enabled", False):
        item.update(status="FAILED", reason="task is disabled")
        return item
    try:
        scheduler_result = int(task.get("LastTaskResult", 0))
    except (TypeError, ValueError):
        item.update(status="UNKNOWN", reason="Task Scheduler LastTaskResult is invalid")
        return item
    if scheduler_result != 0:
        item.update(status="FAILED", reason=f"LastTaskResult={task.get('LastTaskResult')}")
        return item
    if heartbeat is None:
        item.update(status="UNKNOWN", reason="no atomic heartbeat found")
        return item
    item["heartbeat"] = heartbeat
    status = heartbeat.get("status")
    if status in {"FAILED", "TIMED_OUT", "PARTIAL"}:
        item.update(status="FAILED", reason=f"heartbeat status={status}")
        return item
    if status != "SUCCEEDED":
        item.update(status="UNKNOWN", reason=f"heartbeat status={status!r}")
        return item
    finished = _parse_time(heartbeat.get("finished_at_utc"))
    if finished is None:
        item.update(status="UNKNOWN", reason="heartbeat has invalid finished_at_utc")
        return item
    if now - finished > timedelta(hours=max_age_hours):
        item.update(status="STALE", reason=f"heartbeat is older than {max_age_hours}h")
        return item
    item.update(status="SUCCEEDED", reason="scheduler result and recent heartbeat are healthy")
    return item


def load_heartbeat(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def health_report(provider: Callable[[str], dict[str, Any] | None] = query_task, now: datetime | None = None) -> dict[str, Any]:
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    entries = [assess_task(name, project, enabled, hours, provider(name), load_heartbeat(heartbeat_path(name, project)), checked_at) for name, project, enabled, hours in TASKS]
    statuses = {entry["status"] for entry in entries}
    if "FAILED" in statuses or "PARTIAL" in statuses:
        code, overall = 1, "FAILED"
    elif "STALE" in statuses:
        code, overall = 3, "STALE"
    elif "UNKNOWN" in statuses:
        code, overall = 4, "UNKNOWN"
    else:
        code, overall = 0, "HEALTHY"
    return {"checked_at_utc": checked_at.isoformat(timespec="seconds").replace("+00:00", "Z"), "overall_status": overall, "exit_code": code, "automations": entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read Scheduler state and atomic automation heartbeats without executing tasks.")
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON only")
    args = parser.parse_args(argv)
    try:
        report = health_report()
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        report = {"overall_status": "CONFIGURATION_ERROR", "exit_code": 2, "error": str(exc), "automations": []}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"ecosystem health: {report['overall_status']} (exit {report['exit_code']})")
        for entry in report["automations"]:
            print(f"- {entry['task_name']}: {entry['status']} - {entry['reason']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
