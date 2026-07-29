"""Read-only health check for configured operational automations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, NamedTuple

try:
    from tools._win32_compat import CREATE_NO_WINDOW
except ModuleNotFoundError:
    from _win32_compat import CREATE_NO_WINDOW  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASKS_FILE = ROOT / "HEALTH_TASKS.json"


class HealthTask(NamedTuple):
    task_name: str
    project: str
    expected_enabled: bool
    max_age_hours: int
    heartbeat_file: Path | None = None


def _as_task(value: HealthTask | tuple[str, str, bool, int]) -> HealthTask:
    return value if isinstance(value, HealthTask) else HealthTask(*value)


def load_tasks(path: Path = DEFAULT_TASKS_FILE) -> tuple[HealthTask, ...]:
    """Load declarative task metadata; no domain rules are interpreted here."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("health task configuration must be a JSON array")
    tasks: list[HealthTask] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each health task must be a JSON object")
        name, project, enabled, max_age = item.get("task_name"), item.get("project"), item.get("expected_enabled"), item.get("max_age_hours")
        configured_path = item.get("heartbeat_path")
        if not isinstance(name, str) or not name or not isinstance(project, str) or not project or not isinstance(enabled, bool) or not isinstance(max_age, int) or max_age <= 0:
            raise ValueError("health task has invalid task_name, project, expected_enabled, or max_age_hours")
        if configured_path is not None and (not isinstance(configured_path, str) or not configured_path):
            raise ValueError("health task heartbeat_path must be a non-empty string when supplied")
        expanded = Path(os.path.expandvars(configured_path)).expanduser() if configured_path else None
        tasks.append(HealthTask(name, project, enabled, max_age, expanded))
    return tuple(tasks)


# Kept empty in the standalone repository.  Workspace configuration is loaded
# lazily so isolated utility tests remain independent of domain task metadata.
TASKS: tuple[HealthTask | tuple[str, str, bool, int], ...] = ()


def heartbeat_path(task_name: str | HealthTask, project: str | None = None) -> Path:
    if isinstance(task_name, HealthTask):
        if task_name.heartbeat_file is not None:
            return task_name.heartbeat_file
        project, task_name = task_name.project, task_name.task_name
    assert project is not None
    if task_name.endswith("-archival-collection"):
        runtime = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "predictor-tools" / "runtime"
        return runtime / project / task_name / f"{task_name}.heartbeat.json"
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
    # creationflags: sob pythonw.exe (toda tarefa agendada) nao ha console, e
    # este powershell.exe abriria uma janela visivel. Saida ja capturada.
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=15, check=False, creationflags=CREATE_NO_WINDOW)
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


def assess_task(task_name: str, project: str, expected_enabled: bool, max_age_hours: int, task: dict[str, Any] | None, heartbeat: dict[str, Any] | None, now: datetime, heartbeat_file: Path | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"task_name": task_name, "project": project, "expected_enabled": expected_enabled, "heartbeat_path": str(heartbeat_file or heartbeat_path(task_name, project))}
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
    if status in {"SOURCE_UNAVAILABLE", "NO_UPSTREAM_EVENTS"}:
        item.update(status=status, reason=heartbeat.get("operational_status", {}).get("reason", f"heartbeat status={status}"))
        return item
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


def health_report(provider: Callable[[str], dict[str, Any] | None] = query_task, now: datetime | None = None, tasks: tuple[HealthTask | tuple[str, str, bool, int], ...] | None = None) -> dict[str, Any]:
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tasks = (TASKS or load_tasks()) if tasks is None else tasks
    entries = []
    for raw_task in tasks:
        configured = _as_task(raw_task)
        path = heartbeat_path(configured)
        entries.append(assess_task(configured.task_name, configured.project, configured.expected_enabled,
                                   configured.max_age_hours, provider(configured.task_name),
                                   load_heartbeat(path), checked_at, path))
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
    parser.add_argument("--tasks-file", type=Path, default=DEFAULT_TASKS_FILE, help="declarative JSON task configuration")
    args = parser.parse_args(argv)
    try:
        report = health_report(tasks=load_tasks(args.tasks_file))
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
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
