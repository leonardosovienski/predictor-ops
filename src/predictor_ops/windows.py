"""Transitional Windows Task Scheduler adapter; isolated from the portable runtime."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .models import RunStatus


@dataclass(frozen=True)
class TaskQuery:
    status: RunStatus
    task: dict[str, Any] | None
    reason: str | None = None


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def inspect_scheduled_task(name: str) -> TaskQuery:
    if os.name != "nt":
        return TaskQuery(RunStatus.CONFIGURATION_ERROR, None, "Windows Task Scheduler is unavailable")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$t=Get-ScheduledTask -TaskName {_quote(name)};$i=Get-ScheduledTaskInfo -TaskName {_quote(name)};"
        "[pscustomobject]@{name=$t.TaskName;state=[string]$t.State;enabled=[bool]$t.Settings.Enabled;"
        "last_result=[int64]$i.LastTaskResult;last_run=$i.LastRunTime.ToUniversalTime().ToString('o');"
        "next_run=$i.NextRunTime.ToUniversalTime().ToString('o');"
        "actions=@($t.Actions|ForEach-Object {@{execute=$_.Execute;arguments=$_.Arguments;"
        "working_directory=$_.WorkingDirectory}})}"
        "|ConvertTo-Json -Compress -Depth 5"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TaskQuery(RunStatus.CONFIGURATION_ERROR, None, type(exc).__name__)
    if result.returncode:
        return TaskQuery(RunStatus.CONFIGURATION_ERROR, None, f"Task Scheduler query failed ({result.returncode})")
    try:
        value = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return TaskQuery(RunStatus.CONFIGURATION_ERROR, None, "Task Scheduler returned invalid JSON")
    if not isinstance(value, dict) or not isinstance(value.get("enabled"), bool):
        return TaskQuery(RunStatus.CONFIGURATION_ERROR, None, "Task Scheduler returned an invalid task schema")
    if not value["enabled"]:
        return TaskQuery(RunStatus.SKIPPED, value, "task is disabled")
    if value.get("last_result") == 267011 or not value.get("last_run") or str(value["last_run"]).startswith("0001-"):
        return TaskQuery(RunStatus.WAITING, value, "task has never run")
    if value.get("last_result") not in (0, None):
        return TaskQuery(RunStatus.FAILED, value, f"last_result={value.get('last_result')}")
    return TaskQuery(RunStatus.SUCCEEDED, value)


def query_scheduled_task(name: str) -> dict[str, Any] | None:
    """Deprecated 2.x compatibility view. Prefer inspect_scheduled_task()."""
    return inspect_scheduled_task(name).task


def is_overdue(task: dict[str, Any], *, now: datetime | None = None) -> bool:
    raw = task.get("next_run")
    if not isinstance(raw, str):
        return True
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return True
    return (now or datetime.now(UTC)).astimezone(UTC) > deadline
