from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from tools import operational_runner as runner


def invoke(tmp_path: Path, command: list[str], **extra: object) -> tuple[int, Path, Path, Path]:
    log = tmp_path / "human.log"
    heartbeat = tmp_path / "heartbeat.json"
    events = tmp_path / "events.jsonl"
    args = ["run", "--task", "test-task", "--project", "test", "--cwd", str(tmp_path), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--provenance-mode", "permissive"]
    for key, value in extra.items():
        args.extend(["--" + key.replace("_", "-"), str(value)])
    args.extend(["--", *command])
    return runner.main(args), log, heartbeat, events


def read_heartbeat(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_success_records_observable_envelope(tmp_path: Path) -> None:
    code, log, heartbeat, events = invoke(tmp_path, [sys.executable, "-c", "print('ok')"])
    record = read_heartbeat(heartbeat)
    assert code == 0 and record["status"] == "SUCCEEDED"
    assert record["started_at_utc"] and record["finished_at_utc"]
    assert "ok" in log.read_text(encoding="utf-8")
    assert json.loads(events.read_text(encoding="utf-8"))["exit_code"] == 0
    assert record["tools_provenance"]["version"] == "1.1.0"
    assert json.loads(events.read_text(encoding="utf-8"))["tools_provenance"] == record["tools_provenance"]


def test_child_failure_is_propagated(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(7)"])
    assert code == 7
    assert read_heartbeat(heartbeat)["status"] == "FAILED"


def test_timeout_is_observable(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    assert code == 124
    assert read_heartbeat(heartbeat)["status"] == "TIMED_OUT"


def test_lock_skips_second_instance(tmp_path: Path) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    lock = heartbeat.with_suffix(".json.lock")
    lock.write_text("already running", encoding="ascii")
    code, _, actual_heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(0)"])
    assert code == 4
    assert actual_heartbeat == heartbeat
    assert read_heartbeat(heartbeat)["status"] == "SKIPPED"


def test_missing_expected_artifact_is_partial(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(0)"], expected_artifact=tmp_path / "missing.txt")
    assert code == 1
    assert read_heartbeat(heartbeat)["status"] == "PARTIAL"


def test_child_partial_exit_is_preserved_and_observable(tmp_path: Path) -> None:
    code, _, heartbeat, events = invoke(
        tmp_path,
        [sys.executable, "-c", "raise SystemExit(10)"],
        partial_exit_code=10,
    )
    assert code == 10
    assert read_heartbeat(heartbeat)["status"] == "PARTIAL"
    assert json.loads(events.read_text(encoding="utf-8"))["exit_code"] == 10


def test_invalid_working_directory_is_observable(tmp_path: Path) -> None:
    log, heartbeat, events = tmp_path / "x.log", tmp_path / "x.json", tmp_path / "x.jsonl"
    code = runner.main(["run", "--task", "bad", "--project", "test", "--cwd", str(tmp_path / "absent"), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--provenance-mode", "permissive", "--", sys.executable, "-c", "pass"])
    assert code == 3 and read_heartbeat(heartbeat)["status"] == "FAILED"


def test_missing_child_script_is_observable(tmp_path: Path) -> None:
    code, _, heartbeat, _ = invoke(tmp_path, [str(tmp_path / "missing-program.exe")])
    assert code == 3
    assert read_heartbeat(heartbeat)["status"] == "FAILED"


def test_atomic_heartbeat_leaves_no_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.json"
    runner.write_heartbeat(path, {"status": "STARTED"})
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "STARTED"
    assert not list(tmp_path.glob(".heartbeat.json.*.tmp"))


def test_secrets_are_redacted_from_record(tmp_path: Path) -> None:
    _, _, heartbeat, _ = invoke(tmp_path, [sys.executable, "-c", "raise SystemExit(2)", "token=visible"])
    assert "visible" not in heartbeat.read_text(encoding="utf-8")
    assert "token=[REDACTED]" in heartbeat.read_text(encoding="utf-8")


def test_human_log_has_boundary_even_when_child_is_silent(tmp_path: Path) -> None:
    code, log, _, _ = invoke(tmp_path, [sys.executable, "-c", "pass"])
    assert code == 0
    assert "STARTED" in log.read_text(encoding="utf-8") and "SUCCEEDED" in log.read_text(encoding="utf-8")


def test_runner_creates_missing_lock_parent(tmp_path: Path) -> None:
    base = tmp_path / "operations"
    code = runner.main(["run", "--task", "nested", "--project", "test", "--cwd", str(tmp_path), "--log", str(base / "human.log"), "--heartbeat", str(base / "heartbeat.json"), "--event-log", str(base / "events.jsonl"), "--provenance-mode", "permissive", "--", sys.executable, "-c", "pass"])
    assert code == 0
    assert (base / "heartbeat.json").is_file() and not (base / "heartbeat.json.lock").exists()


def test_consumer_metadata_is_additive_and_redacted(tmp_path: Path) -> None:
    metadata = json.dumps({"project": "example", "project_commit": "abc", "token": "do-not-persist"})
    code, _, heartbeat, _ = invoke(
        tmp_path, [sys.executable, "-c", "pass"], consumer_provenance_json=metadata,
    )
    record = read_heartbeat(heartbeat)
    assert code == 0
    assert record["consumer_provenance"]["project_commit"] == "abc"
    assert record["consumer_provenance"]["token"] == "[REDACTED]"
