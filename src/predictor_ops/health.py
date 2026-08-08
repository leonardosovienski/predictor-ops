from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import RunStatus
from .windows import TaskQuery


class HealthPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    heartbeat_path: Path
    max_age_seconds: float = Field(gt=0)
    expected_enabled: bool = True


def load_heartbeat(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def assess(policy: HealthPolicy, scheduler: TaskQuery | None, *, now: datetime | None = None) -> dict[str, Any]:
    checked = (now or datetime.now(UTC)).astimezone(UTC)
    result: dict[str, Any] = {"job_id": policy.job_id, "checked_at": checked.isoformat(), "status": "FAILED"}
    if scheduler is not None:
        result["scheduler_status"] = scheduler.status
        if not policy.expected_enabled and scheduler.status is RunStatus.SKIPPED:
            return {**result, "status": RunStatus.SKIPPED, "reason": "expected disabled"}
        if scheduler.status not in {RunStatus.SUCCEEDED, RunStatus.WAITING}:
            return {**result, "status": scheduler.status, "reason": scheduler.reason}
    heartbeat = load_heartbeat(policy.heartbeat_path)
    if heartbeat is None:
        return {**result, "status": RunStatus.FAILED, "reason": "heartbeat unavailable"}
    try:
        status = RunStatus(heartbeat["run_status"])
    except (KeyError, ValueError, TypeError):
        return {**result, "status": RunStatus.FAILED, "reason": "heartbeat status invalid"}
    if status is not RunStatus.SUCCEEDED:
        return {**result, "status": status, "reason": "terminal heartbeat is not successful"}
    raw_finished = heartbeat.get("finished_at")
    try:
        finished = datetime.fromisoformat(str(raw_finished).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return {**result, "status": RunStatus.FAILED, "reason": "heartbeat time invalid"}
    if checked - finished > timedelta(seconds=policy.max_age_seconds):
        return {**result, "status": RunStatus.FAILED, "reason": "heartbeat stale"}
    return {**result, "status": RunStatus.SUCCEEDED, "reason": "healthy", "heartbeat": heartbeat}
