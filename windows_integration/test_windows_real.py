import os
import subprocess
import time
import uuid

import pytest

from predictor_ops.models import OperationalState
from predictor_ops.windows import inspect_scheduled_task


def _powershell(script):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def task_name():
    name = f"predictor-ops-ci-{uuid.uuid4().hex}"
    create = _powershell(
        f"$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit 7';"
        f"$t=New-ScheduledTaskTrigger -Once -At (Get-Date).AddHours(1);"
        f"Register-ScheduledTask -TaskName '{name}' -Action $a -Trigger $t -Force | Out-Null"
    )
    assert create.returncode == 0, create.stderr
    try:
        yield name
    finally:
        _powershell(f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue")


def test_real_powershell_and_missing_task_fail_closed():
    assert os.name == "nt"
    version = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
        capture_output=True,
        text=True,
    )
    assert version.returncode == 0 and version.stdout.strip()
    result = inspect_scheduled_task("predictor-ops-ci-definitely-absent")
    assert result.status is OperationalState.CONFIGURATION_ERROR


def test_real_present_never_run_disabled_and_failed_task(task_name):
    never = inspect_scheduled_task(task_name)
    assert never.status is OperationalState.WAITING and never.task is not None
    assert never.task["actions"][0]["execute"] == "cmd.exe"
    disabled = _powershell(f"Disable-ScheduledTask -TaskName '{task_name}' | Out-Null")
    assert disabled.returncode == 0
    assert inspect_scheduled_task(task_name).status is OperationalState.SKIPPED
    started = _powershell(
        f"Enable-ScheduledTask -TaskName '{task_name}' | Out-Null; Start-ScheduledTask -TaskName '{task_name}'"
    )
    assert started.returncode == 0
    deadline = time.monotonic() + 10
    result = inspect_scheduled_task(task_name)
    while time.monotonic() < deadline and result.status is OperationalState.WAITING:
        time.sleep(0.2)
        result = inspect_scheduled_task(task_name)
    assert result.status is OperationalState.FAILED and result.task is not None
    assert result.task["last_result"] == 7
