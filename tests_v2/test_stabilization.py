import io
import json
import subprocess
import sys
import threading
import time
import tracemalloc
from datetime import UTC, datetime, timedelta

import pytest
from test_operational_safety import execution

import predictor_ops.runner as runner
from predictor_ops.models import JobConfig, JobType, RuntimeConfig
from predictor_ops.runtime import backend


def test_early_persistence_failure_releases_lock(tmp_path, monkeypatch):
    job = JobConfig(
        id="blocked",
        command=[sys.executable, "-c", "raise AssertionError('must not run')"],
        job_type=JobType.EXECUTION,
        capital_permission=True,
        runtime=RuntimeConfig(root=tmp_path),
    )

    def fail(*args):
        raise OSError("fixture persistence failure")

    monkeypatch.setattr(runner, "atomic_json", fail)
    with pytest.raises(OSError):
        runner.run_job(job)
    lock = backend(job.runtime).acquire(job.id, "retry", 60)
    try:
        assert lock.acquired
    finally:
        lock.release()


def test_skipped_metadata_is_redacted_before_persistence(tmp_path):
    secret = "fixture-super-secret-123456"
    job = JobConfig(
        id="blocked",
        command=[sys.executable, "-c", "raise AssertionError('must not run')"],
        job_type=JobType.EXECUTION,
        capital_permission=True,
        runtime=RuntimeConfig(root=tmp_path),
        environment={"API_TOKEN": secret},
        input_reference=secret,
        scientific_state=secret,
    )
    result = runner.run_job(job)
    assert secret not in json.dumps(result.record)
    for path in tmp_path.rglob("*.json*"):
        assert secret not in path.read_text()


def test_capture_memory_is_bounded_before_newline():
    # Allocate fixture before tracing: measure the reader, not fixture storage.
    stream = io.BytesIO(b"x" * (8 * 1024 * 1024))
    sink, truncated, errors = bytearray(), threading.Event(), []
    tracemalloc.start()
    try:
        runner._drain(stream, sink, (), 1024, truncated, errors)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert not errors
    assert len(sink) == 1024 and truncated.is_set()
    assert peak < 1024 * 1024, peak


def test_capture_redacts_secret_across_capture_boundary():
    secret = "fixture-super-secret-123456"
    sink, truncated, errors = bytearray(), threading.Event(), []
    runner._drain(io.BytesIO(b"x" * 1010 + secret.encode()), sink, (secret,), 1024, truncated, errors)
    assert not errors
    assert b"fixture-super" not in sink


def test_exited_parent_with_inherited_stdout_is_bounded_and_isolated(tmp_path):
    marker = tmp_path / "descendant-started"
    child = f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(12)"
    parent = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"p=Path({str(marker)!r}); "
        "exec('while not p.exists(): time.sleep(0.01)')"
    )
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        started = time.monotonic()
        result = runner.run_job(
            JobConfig(
                id="orphan",
                command=[sys.executable, "-c", parent],
                runtime=RuntimeConfig(root=tmp_path / "runtime"),
                heartbeat_interval_seconds=0.02,
            )
        )
        elapsed = time.monotonic() - started
        assert result.exit_code == 0
        assert marker.exists()
        assert elapsed < 8, elapsed
        assert foreign.poll() is None
    finally:
        foreign.terminate()
        foreign.wait(5)


@pytest.mark.parametrize("condition", ["missing", "incomplete", "stale", "future", "limits"])
def test_risk_blocks_have_no_subprocess_effect(tmp_path, condition):
    marker = tmp_path / "forbidden-effect"
    job = execution(tmp_path, f"from pathlib import Path; Path({str(marker)!r}).touch()")
    if condition == "missing":
        job = job.model_copy(update={"risk_snapshot": None})
    elif condition == "limits":
        job = job.model_copy(
            update={"kill_switch_limits": job.kill_switch_limits.model_copy(update={"max_daily_loss": None})}
        )
    else:
        assert job.risk_snapshot is not None
        updates = (
            {"source": None}
            if condition == "incomplete"
            else {"observed_at": datetime.now(UTC) + timedelta(seconds=-120 if condition == "stale" else 120)}
        )
        job = job.model_copy(update={"risk_snapshot": job.risk_snapshot.model_copy(update=updates)})
    result = runner.run_job(job)
    assert result.record["reason"] == "kill_switch_open"
    assert not marker.exists()


def test_unknown_submission_is_preserved_without_reexecution(tmp_path):
    marker = tmp_path / "attempts"
    code = f"from pathlib import Path; p=Path({str(marker)!r}); p.write_text('attempt'); raise SystemExit(9)"
    first = runner.run_job(execution(tmp_path, code))
    assert first.exit_code == 9
    attempt = next((tmp_path / "idempotency").glob("*.json"))
    preserved = attempt.read_bytes()
    second = runner.run_job(
        execution(tmp_path, f"from pathlib import Path; Path({str(marker)!r}).write_text('repeated')")
    )
    assert second.record["previous_attempt"]["requires_reconciliation"] is True
    assert attempt.read_bytes() == preserved
    assert marker.read_text() == "attempt"
