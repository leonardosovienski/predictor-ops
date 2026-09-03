import json
import sys
import threading

from predictor_ops.models import JobConfig, RunStatus, RuntimeConfig
from predictor_ops.observability import configure_otel, logger
from predictor_ops.redaction import REDACTED, redact, redact_text, sensitive_values
from predictor_ops.runner import run_job
from predictor_ops.runtime import LocalBackend


def job(tmp_path, code, **values):
    return JobConfig(
        id=values.pop("id", "test"),
        command=[sys.executable, "-c", code],
        runtime=RuntimeConfig(root=tmp_path, lock_stale_after_seconds=60),
        heartbeat_interval_seconds=0.05,
        **values,
    )


def test_success_provenance_and_artifacts(tmp_path):
    result = run_job(
        job(
            tmp_path,
            "print('ok')",
            provenance={"commit": "abc"},
            config_version="jobs-v4",
            input_reference="dataset:sha256:abc",
            output_reference="artifact:forecast-42",
            retry_count=2,
            host_or_environment="ci-linux",
        )
    )
    assert result.run_status is RunStatus.SUCCEEDED
    assert result.record["provenance"] == {"commit": "abc"}
    assert result.record["config_version"] == "jobs-v4"
    assert result.record["input_reference"] == "dataset:sha256:abc"
    assert result.record["output_reference"] == "artifact:forecast-42"
    assert result.record["retry_count"] == 2
    assert result.record["host_or_environment"] == "ci-linux"
    assert json.loads((tmp_path / "test" / "heartbeat.json").read_text())["run_status"] == "SUCCEEDED"
    assert len((tmp_path / "test" / "events.jsonl").read_text().splitlines()) == 1


def test_concurrent_run_is_skipped(tmp_path):
    runtime = LocalBackend(tmp_path)
    lock = runtime.acquire("same", "owner", 60)
    result = run_job(job(tmp_path, "print('never')", id="same"), runtime_backend=runtime)
    assert result.run_status is RunStatus.SKIPPED
    lock.release()


def test_timeout_and_truncation(tmp_path):
    result = run_job(
        job(
            tmp_path,
            "import time; print('x'*1000, flush=True); time.sleep(5)",
            timeout_seconds=0.2,
            max_output_bytes=20,
        )
    )
    assert result.exit_code == 124 and result.run_status is RunStatus.FAILED
    assert result.record["termination"]["reason"] == "timeout"
    assert result.record["output"]["truncated"] and result.record["output"]["bytes"] == 20


def test_crash_and_missing_expected_artifact(tmp_path):
    assert run_job(job(tmp_path, "raise SystemExit(9)", id="crash")).exit_code == 9
    result = run_job(job(tmp_path, "pass", id="artifact", expected_artifact=tmp_path / "missing"))
    assert result.run_status is RunStatus.PARTIAL


def test_shutdown(tmp_path):
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    result = run_job(job(tmp_path, "import time; time.sleep(5)", id="shutdown"), shutdown=stop)
    assert result.exit_code == 130 and result.record["termination"]["reason"] == "shutdown"


def test_redacts_environment_arguments_stdout_and_stderr(tmp_path):
    secret = "super-secret-123"
    code = "import os,sys; s=os.environ['API_TOKEN']; print(s); print('password='+s,file=sys.stderr)"
    configured = job(tmp_path, code, environment={"API_TOKEN": secret}, provenance={"authorization": secret})
    configured.command.append(f"token={secret}")
    result = run_job(configured)
    serialized = json.dumps(result.record)
    assert secret not in serialized
    assert REDACTED in serialized
    assert redact({"token": secret}, (secret,))["token"] == REDACTED
    assert sensitive_values({"API_TOKEN": secret}) == (secret,)
    assert secret not in redact_text(f"Bearer {secret}", (secret,))


def test_json_logger_and_disabled_otel():
    configure_otel(None)
    value = logger()
    record = value.makeRecord(value.name, 20, __file__, 1, "test_event", (), None, extra={"fields": {"job_id": "x"}})
    formatter = value.handlers[0].formatter
    assert formatter is not None
    assert '"event": "test_event"' in formatter.format(record)
