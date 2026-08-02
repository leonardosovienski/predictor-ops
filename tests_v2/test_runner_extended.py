import json
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from predictor_ops.models import JobConfig, OperationalState, RuntimeConfig
from predictor_ops.runner import run_job
from predictor_ops.runtime import LocalBackend, append_jsonl, atomic_json


def _job(tmp_path, code="pass", **kwargs):
    return JobConfig(
        id=kwargs.pop("id", "extended"),
        command=[sys.executable, "-c", code],
        heartbeat_interval_seconds=0.02,
        runtime=RuntimeConfig(root=tmp_path),
        **kwargs,
    )


def test_partial_exit_and_consumer_status(tmp_path):
    partial = run_job(_job(tmp_path, "raise SystemExit(2)", id="partial"))
    assert partial.exit_code == 2 and partial.status is OperationalState.PARTIAL
    source = run_job(_job(tmp_path, id="source", consumer_status=OperationalState.SOURCE_UNAVAILABLE))
    assert source.status is OperationalState.SOURCE_UNAVAILABLE


def test_strict_setup_failure_is_terminal_and_child_never_runs(tmp_path):
    marker = tmp_path / "must-not-exist"
    result = run_job(_job(tmp_path, f"open({str(marker)!r},'w').write('bad')", id="strict", provenance_mode="strict"))
    assert result.status is OperationalState.CONFIGURATION_ERROR and result.exit_code == 3
    assert not marker.exists()
    heartbeat = json.loads((tmp_path / "strict" / "heartbeat.json").read_text())
    assert heartbeat["status"] == "CONFIGURATION_ERROR" and "editable" in heartbeat["error"]


class LosingLock:
    acquired = True

    def __init__(self):
        self.released = False

    def refresh(self):
        return False

    def release(self):
        self.released = True


class LosingBackend:
    def __init__(self):
        self.lock = LosingLock()

    def acquire(self, job_id: str, run_id: str, ttl: float):
        return self.lock


def test_lock_loss_terminates_and_cleans_up(tmp_path):
    backend = LosingBackend()
    result = run_job(_job(tmp_path, "import time; time.sleep(5)", id="lost"), runtime_backend=backend)
    assert result.exit_code == 75 and result.record["termination"]["reason"] == "lock_lost"
    assert backend.lock.released


def test_atomic_failure_leaves_no_temporary_and_preserves_previous(tmp_path, monkeypatch):
    path = tmp_path / "heartbeat.json"
    atomic_json(path, {"old": True})
    monkeypatch.setattr("predictor_ops.runtime.os.replace", lambda *args: (_ for _ in ()).throw(OSError("fail")))
    with pytest.raises(OSError):
        atomic_json(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_jsonl_concurrent_writers_are_parseable(tmp_path):
    path = tmp_path / "events.jsonl"
    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(lambda index: append_jsonl(path, {"index": index}), range(100)))
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert sorted(record["index"] for record in records) == list(range(100))


def test_terminal_persistence_failure_still_releases_lock(tmp_path, monkeypatch):
    backend = LocalBackend(tmp_path)
    original = __import__("predictor_ops.runner", fromlist=["atomic_json"]).atomic_json
    calls = 0

    def fail_terminal(path, payload):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("disk full")
        original(path, payload)

    monkeypatch.setattr("predictor_ops.runner.atomic_json", fail_terminal)
    with pytest.raises(OSError, match="persistence"):
        run_job(_job(tmp_path, id="persist"), runtime_backend=backend)
    assert backend.acquire("persist", "successor", 60).acquired
