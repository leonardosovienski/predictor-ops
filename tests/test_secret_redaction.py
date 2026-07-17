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


def test_cli_scan_and_dry_run_are_redacted(tmp_path: Path, monkeypatch, capsys) -> None:
    source = _write_fake_source(tmp_path)
    monkeypatch.setenv("FICTITIOUS_API_KEY", FAKE_KEY)
    assert redaction.main(["scan", str(source)]) == 0
    scanned = capsys.readouterr().out
    assert FAKE_KEY not in scanned and FAKE_TOKEN not in scanned
    assert redaction.main(["sanitize", str(source), "--dry-run"]) == 0
    assert '"dry_run": true' in capsys.readouterr().out


def _write_fake_source(tmp_path: Path) -> Path:
    source = tmp_path / "source.log"
    source.write_text(f"token={FAKE_TOKEN}\n", encoding="utf-8")
    return source


# Onda 3: o código não deve conhecer nomes de fornecedores específicos
# (ex.: CoinGecko). Estes testes provam que um header vendor-specific como
# x-cg-demo-api-key continua sendo redigido pela regra GENÉRICA de
# "*api*key*", mesmo sem existir como literal em nenhum lugar do módulo.
FAKE_VENDOR_KEY = "cg_demo_fake_1234567890"


def test_no_vendor_specific_literal_in_module_source() -> None:
    import inspect
    source = inspect.getsource(redaction)
    assert "coingecko" not in source.lower()
    assert "x-cg-demo-api-key" not in source.lower()


def test_vendor_style_header_key_value_pair_is_redacted_generically() -> None:
    # Estilo "header: valor" (o mesmo padrão de qualquer header HTTP de auth).
    sanitized = redaction.redact_text(f"x-cg-demo-api-key: {FAKE_VENDOR_KEY}")
    assert FAKE_VENDOR_KEY not in sanitized
    assert redaction.REDACTED in sanitized


def test_vendor_style_header_case_insensitive_is_redacted() -> None:
    sanitized = redaction.redact_text(f"X-CG-Demo-API-Key: {FAKE_VENDOR_KEY}")
    assert FAKE_VENDOR_KEY not in sanitized


def test_vendor_style_header_as_url_query_param_is_redacted() -> None:
    url = f"https://api.coingecko.com/v3/ping?x-cg-demo-api-key={FAKE_VENDOR_KEY}"
    sanitized = redaction.redact_text(url)
    assert FAKE_VENDOR_KEY not in sanitized


def test_vendor_style_header_in_mapping_is_redacted() -> None:
    payload = {"x-cg-demo-api-key": FAKE_VENDOR_KEY, "count": 3}
    sanitized = redaction.redact_mapping(payload)
    assert sanitized["x-cg-demo-api-key"] == redaction.REDACTED
    assert FAKE_VENDOR_KEY not in json.dumps(sanitized)


def test_multiple_secrets_in_same_message_are_all_redacted() -> None:
    text = f"api_key={FAKE_KEY} token={FAKE_TOKEN} password=another_fake_secret_val"
    sanitized = redaction.redact_text(text)
    assert FAKE_KEY not in sanitized
    assert FAKE_TOKEN not in sanitized
    assert "another_fake_secret_val" not in sanitized
    assert sanitized.count(redaction.REDACTED) >= 3


def test_empty_value_is_left_unmatched() -> None:
    assert redaction.redact_text("api_key=") == "api_key="


def test_short_value_under_sensitive_key_is_still_redacted_by_assignment_rule() -> None:
    # ASSIGNMENT redige qualquer valor sob uma chave sensível, independente do
    # comprimento — só collect_sensitive_values() (para valores CONHECIDOS via
    # env/config) exige MIN_SECRET_LENGTH; a regra estrutural não.
    assert redaction.redact_text("token=abc") == f"token={redaction.REDACTED}"


def test_redact_mapping_redacts_known_secret_used_as_dict_key() -> None:
    # Regressão (auditoria hostil 2026-07-17): redact_mapping só checava o
    # NOME da chave (ex.: "api_key"). Se o próprio VALOR de um segredo
    # conhecido fosse usado como chave (padrão comum: indexar por
    # token/session-id), ele vazava verbatim, mesmo estando em
    # sensitive_values. O valor da chave aqui é deliberadamente opaco (não
    # contém "token"/"secret"/"key"/etc.) para exercitar o caminho NOVO, não
    # a checagem de nome já existente.
    session_id = "9f8e7d6c5b4a3210deadbeefcafebabe12345678"
    payload = {session_id: "some value", "other": "fine"}
    sanitized = redaction.redact_mapping(payload, [session_id])
    assert session_id not in sanitized
    assert redaction.REDACTED in sanitized
    assert sanitized[redaction.REDACTED] == "some value"
    assert sanitized["other"] == "fine"
