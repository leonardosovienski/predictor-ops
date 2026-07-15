from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from tools import operational_runner as runner
from tools import secret_redaction as redaction


FAKE_KEY = "fake_api_key_123456789"
FAKE_TOKEN = "fake_token_987654321"


def test_plain_text_and_short_value_are_preserved() -> None:
    assert redaction.redact_text("ordinary diagnostic count=7") == "ordinary diagnostic count=7"
    assert redaction.redact_text("mode=dev") == "mode=dev"


def test_assignments_bearer_headers_json_and_urls_are_redacted() -> None:
    text = (
        f"api_key={FAKE_KEY} Bearer {FAKE_TOKEN}\n"
        f"Authorization: Bearer {FAKE_TOKEN}\n"
        f'{{"token":"{FAKE_TOKEN}"}}\n'
        f"https://user:password@example.test/path?api_key={FAKE_KEY}&page=2"
    )
    sanitized = redaction.redact_text(text)
    assert FAKE_KEY not in sanitized and FAKE_TOKEN not in sanitized
    assert sanitized.count(redaction.REDACTED) >= 5
    assert "page=2" in sanitized


def test_mapping_and_known_environment_values_are_redacted(monkeypatch) -> None:
    monkeypatch.setenv("FICTITIOUS_API_KEY", FAKE_KEY)
    values = redaction.collect_sensitive_values(os.environ)
    payload = {"password": FAKE_TOKEN, "nested": {"message": f"value={FAKE_KEY}"}, "count": 3}
    sanitized = redaction.redact_mapping(payload, values)
    assert sanitized["password"] == redaction.REDACTED
    assert FAKE_KEY not in json.dumps(sanitized)


def test_redaction_is_idempotent_and_accepts_bytes() -> None:
    once = redaction.redact_text(f"token={FAKE_TOKEN}".encode("utf-8"))
    assert redaction.redact_text(once) == once
    assert FAKE_TOKEN not in once


def test_command_redacts_separate_and_equals_arguments() -> None:
    command = ["tool", "--api-key", FAKE_KEY, f"--token={FAKE_TOKEN}"]
    sanitized = redaction.redact_command(command)
    assert sanitized[2] == redaction.REDACTED
    assert FAKE_KEY not in " ".join(sanitized) and FAKE_TOKEN not in " ".join(sanitized)


def test_safe_redaction_never_returns_raw_when_internal_redactor_fails(monkeypatch) -> None:
    monkeypatch.setattr(redaction, "redact_text", lambda *_: (_ for _ in ()).throw(RuntimeError("fail")))
    assert redaction.safe_redact_text(FAKE_TOKEN) == redaction.REDACTION_FAILED


def test_history_scan_and_atomic_sanitization_do_not_emit_secret(tmp_path: Path) -> None:
    source = tmp_path / "historical.log"
    source.write_text(f"request api_key={FAKE_KEY}\n", encoding="utf-8")
    report = redaction.scan_path(source)
    assert report["occurrence_count"] == 1
    assert FAKE_KEY not in json.dumps(report)
    destination = tmp_path / "historical.sanitized.log"
    redaction.atomic_sanitize(source, destination)
    assert FAKE_KEY not in destination.read_text(encoding="utf-8")
    assert destination.stat().st_mtime_ns == source.stat().st_mtime_ns


def test_wrapper_redacts_stdout_stderr_command_heartbeat_and_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FICTITIOUS_API_KEY", FAKE_KEY)
    log, heartbeat, events = tmp_path / "human.log", tmp_path / "heartbeat.json", tmp_path / "events.jsonl"
    child = f"import sys; print('api_key={FAKE_KEY}'); print('Bearer {FAKE_TOKEN}', file=sys.stderr); raise SystemExit(9)"
    code = runner.main(["run", "--task", "test", "--project", "test", "--cwd", str(tmp_path), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--provenance-mode", "permissive", "--", sys.executable, "-c", child, "--token", FAKE_TOKEN])
    assert code == 9
    produced = [log, heartbeat, events]
    for artifact in produced:
        contents = artifact.read_text(encoding="utf-8")
        assert FAKE_KEY not in contents and FAKE_TOKEN not in contents
        assert redaction.REDACTED in contents


def test_wrapper_persists_no_raw_output_when_redactor_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FICTITIOUS_API_KEY", FAKE_KEY)
    monkeypatch.setattr(runner, "safe_redact_text", lambda *_: redaction.REDACTION_FAILED)
    log, heartbeat, events = tmp_path / "human.log", tmp_path / "heartbeat.json", tmp_path / "events.jsonl"
    child = f"print('token={FAKE_TOKEN}')"
    code = runner.main(["run", "--task", "test", "--project", "test", "--cwd", str(tmp_path), "--log", str(log), "--heartbeat", str(heartbeat), "--event-log", str(events), "--provenance-mode", "permissive", "--", sys.executable, "-c", child])
    assert code == 0
    assert FAKE_TOKEN not in log.read_text(encoding="utf-8")
    assert redaction.REDACTION_FAILED in log.read_text(encoding="utf-8")


def test_no_fictitious_secret_remains_in_generated_artifacts(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generated.mkdir()
    destination = generated / "sanitized.log"
    redaction.atomic_sanitize(_write_fake_source(tmp_path), destination)
    for path in generated.rglob("*"):
        if path.is_file():
            assert FAKE_KEY not in path.read_text(encoding="utf-8")
            assert FAKE_TOKEN not in path.read_text(encoding="utf-8")


def _write_fake_source(tmp_path: Path) -> Path:
    source = tmp_path / "source.log"
    source.write_text(f"token={FAKE_TOKEN}\n", encoding="utf-8")
    return source
