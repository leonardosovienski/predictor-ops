from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "brasileirao-predictor" / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entrypoint_builds_task_specific_wrapper_command(monkeypatch) -> None:
    entrypoint = load_module("sombra_entrypoint_test", "sombra_diaria.py")
    observed: list[list[str]] = []
    monkeypatch.setattr(entrypoint.subprocess, "run", lambda command, **_: observed.append(command) or SimpleNamespace(returncode=7))
    assert entrypoint.main(["--task-name", "brasileirao-sombra-manha"]) == 7
    command = observed[0]
    assert "--task" in command and command[command.index("--task") + 1] == "brasileirao-sombra-manha"
    assert "--timeout" in command and command[command.index("--timeout") + 1] == "7200"
    assert "sombra_diaria_payload.py" in " ".join(command)


@pytest.mark.parametrize("failed_step", ["ingest", "capture", "settle"])
def test_payload_propagates_any_step_failure_and_redacts_output(tmp_path: Path, monkeypatch, failed_step: str) -> None:
    payload = load_module(f"sombra_payload_{failed_step}", "sombra_diaria_payload.py")
    payload.LOG = tmp_path / "sombra.log"
    payload.PASSOS = [(name, [name], 1) for name in ("ingest", "capture", "settle")]
    monkeypatch.setattr(payload, "SENSITIVE_VALUES", ("fake_secret_value_123",))

    def fake_run(command, **_):
        code = 1 if command[0] == failed_step else 0
        return SimpleNamespace(returncode=code, stdout="token=fake_secret_value_123", stderr="token=fake_secret_value_123")

    monkeypatch.setattr(payload.subprocess, "run", fake_run)
    assert payload.main() == 1
    log = payload.LOG.read_text(encoding="utf-8")
    assert "fake_secret_value_123" not in log and "[REDACTED]" in log


def test_payload_success_is_zero(tmp_path: Path, monkeypatch) -> None:
    payload = load_module("sombra_payload_success", "sombra_diaria_payload.py")
    payload.LOG = tmp_path / "sombra.log"
    payload.PASSOS = [("ingest", ["ingest"], 1)]
    monkeypatch.setattr(payload.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    assert payload.main() == 0
