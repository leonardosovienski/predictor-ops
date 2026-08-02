import ctypes
import gc
import os
import subprocess
import sys
import threading
import warnings
from pathlib import Path

import pytest

import predictor_ops.runner as runner
from predictor_ops.models import JobConfig, OperationalState, RuntimeConfig


def _job(tmp_path: Path, code: str, **kwargs) -> JobConfig:
    return JobConfig(
        id=kwargs.pop("id", "cleanup"),
        command=[sys.executable, "-c", code],
        runtime=RuntimeConfig(root=tmp_path),
        heartbeat_interval_seconds=0.02,
        **kwargs,
    )


def _resource_count() -> int:
    if os.name == "nt":
        count = ctypes.c_ulong()
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetProcessHandleCount.restype = ctypes.c_int
        assert kernel32.GetProcessHandleCount(kernel32.GetCurrentProcess(), ctypes.byref(count))
        return count.value
    return len(list(Path("/proc/self/fd").iterdir()))


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("print('ok')", OperationalState.SUCCEEDED),
        ("raise SystemExit(9)", OperationalState.FAILED),
        ("raise SystemExit(2)", OperationalState.PARTIAL),
    ],
)
def test_all_normal_exit_paths_close_popen_streams(tmp_path, monkeypatch, code, expected):
    created = []
    real_popen = subprocess.Popen

    def tracking_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", tracking_popen)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        result = runner.run_job(_job(tmp_path, code))
        gc.collect()
    assert result.status is expected
    direct = next(process for process in reversed(created) if process.args == [sys.executable, "-c", code])
    assert direct.poll() is not None
    assert direct.stdin is None or direct.stdin.closed
    assert direct.stdout is None or direct.stdout.closed
    assert direct.stderr is None or direct.stderr.closed
    assert not [warning for warning in caught if issubclass(warning.category, ResourceWarning)]


def test_timeout_and_cancellation_close_reader_and_pipe(tmp_path):
    timeout = runner.run_job(_job(tmp_path, "import time; time.sleep(30)", id="timeout", timeout_seconds=0.1))
    stop = threading.Event()
    stop.set()
    cancelled = runner.run_job(_job(tmp_path, "import time; time.sleep(30)", id="cancel"), shutdown=stop)
    assert timeout.exit_code == 124 and cancelled.exit_code == 130
    assert not [thread for thread in threading.enumerate() if thread.name.startswith("predictor-ops-output-")]


def test_exception_after_popen_terminates_child_and_closes_pipe(tmp_path, monkeypatch):
    created = []
    real_popen, real_atomic = subprocess.Popen, runner.atomic_json
    failed = False

    def tracking_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        return process

    def fail_once(path, payload):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("heartbeat unavailable")
        real_atomic(path, payload)

    monkeypatch.setattr(runner.subprocess, "Popen", tracking_popen)
    monkeypatch.setattr(runner, "atomic_json", fail_once)
    result = runner.run_job(_job(tmp_path, "import time; time.sleep(30)", id="setup-error"))
    assert result.status is OperationalState.CONFIGURATION_ERROR
    direct = created[-1]
    assert direct.poll() is not None and direct.stdout.closed


def test_reader_failure_is_observable_and_resources_close(tmp_path, monkeypatch):
    def broken_reader(stream, sink, secrets, limit, truncated, errors):
        errors.append(OSError("simulated read failure"))

    monkeypatch.setattr(runner, "_drain", broken_reader)
    result = runner.run_job(_job(tmp_path, "print('unread')", id="read-failure"))
    assert result.status is OperationalState.FAILED and result.exit_code == 74
    assert "simulated read failure" in result.record["error"]


def test_repeated_runs_do_not_accumulate_handles_or_readers(tmp_path):
    gc.collect()
    before = _resource_count()
    for index in range(30):
        result = runner.run_job(_job(tmp_path, "print('ok')", id=f"repeat-{index}"))
        assert result.status is OperationalState.SUCCEEDED
    gc.collect()
    after = _resource_count()
    assert after <= before + 2, (before, after)
    assert not [thread for thread in threading.enumerate() if thread.name.startswith("predictor-ops-output-")]


def test_large_stdout_and_stderr_are_drained_without_deadlock(tmp_path):
    code = "import os\nchunk=b'x'*65536\nfor _ in range(32):\n os.write(1,chunk); os.write(2,chunk)\n"
    result = runner.run_job(_job(tmp_path, code, id="large-output", timeout_seconds=10, max_output_bytes=5_000_000))
    assert result.status is OperationalState.SUCCEEDED
    assert result.record["output"]["bytes"] == 4 * 1024 * 1024
    assert not result.record["output"]["truncated"]
