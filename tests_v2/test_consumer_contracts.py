import json
import sys
from pathlib import Path

import pytest

from predictor_ops.compat.legacy import translate_legacy_runner
from predictor_ops.models import RunStatus
from predictor_ops.runner import run_job


def _legacy(tmp_path: Path, consumer: str, code: str, *, timeout: float = 2):
    runtime = tmp_path / "runtime" / consumer
    argv = [
        "run",
        "--task",
        f"{consumer}-job",
        "--project",
        consumer,
        "--cwd",
        str(tmp_path),
        "--timeout",
        str(timeout),
        "--heartbeat",
        str(runtime / "heartbeat.json"),
        "--events",
        str(runtime / "events.jsonl"),
        "--lock",
        str(runtime / "run.lock"),
        "--provenance-mode",
        "permissive",
        "--consumer-provenance-json",
        json.dumps({"consumer": consumer, "token": "fixture-secret"}),
        "--",
        sys.executable,
        "-c",
        code,
    ]
    with pytest.deprecated_call():
        return translate_legacy_runner(argv)


def _assert_contract(tmp_path, consumer):
    config = _legacy(tmp_path, consumer, "print('token=fixture-secret')")
    result = run_job(config)
    assert result.run_status is RunStatus.SUCCEEDED
    assert result.record["provenance"]["legacy_project"] == consumer
    serialized = json.dumps(result.record)
    assert "fixture-secret" not in serialized
    root = config.runtime.root / config.id
    assert json.loads((root / "heartbeat.json").read_text())["run_status"] == "SUCCEEDED"
    assert len((root / "events.jsonl").read_text().splitlines()) == 1


def test_brasileirao_consumer_translation_contract(tmp_path):
    _assert_contract(tmp_path, "brasileirao-predictor")


def test_cs_consumer_translation_contract(tmp_path):
    _assert_contract(tmp_path, "cs-predictor")


def test_lol_consumer_translation_contract(tmp_path):
    _assert_contract(tmp_path, "lol-predictor")


def test_f1_consumer_translation_contract(tmp_path):
    _assert_contract(tmp_path, "f1-predictor")


def test_crypto_consumer_translation_contract(tmp_path):
    _assert_contract(tmp_path, "previsao-cripto")


def test_consumer_failure_partial_and_timeout_contracts(tmp_path):
    failed = run_job(_legacy(tmp_path, "failed", "raise SystemExit(7)"))
    partial = run_job(_legacy(tmp_path, "partial", "raise SystemExit(2)"))
    timeout = run_job(_legacy(tmp_path, "timeout", "import time; time.sleep(10)", timeout=0.2))
    assert (failed.run_status, failed.exit_code) == (RunStatus.FAILED, 7)
    assert (partial.run_status, partial.exit_code) == (RunStatus.PARTIAL, 2)
    assert (timeout.run_status, timeout.exit_code) == (RunStatus.FAILED, 124)


def test_legacy_explicit_paths_must_share_directory(tmp_path):
    with pytest.deprecated_call(), pytest.raises(ValueError, match="share"):
        translate_legacy_runner(
            [
                "run",
                "--task",
                "x",
                "--heartbeat",
                str(tmp_path / "one" / "h.json"),
                "--events",
                str(tmp_path / "two" / "e.jsonl"),
                "--",
                "echo",
            ]
        )
