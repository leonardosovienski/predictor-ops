from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "cs-predictor" / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entrypoint_uses_the_shared_operational_contract(monkeypatch) -> None:
    entrypoint = load_module("cs_entrypoint_test", "atualiza_semanal.py")
    seen: list[list[str]] = []
    monkeypatch.setattr(entrypoint.subprocess, "run", lambda command, **_: seen.append(command) or SimpleNamespace(returncode=5))
    assert entrypoint.main([]) == 5
    command = seen[0]
    assert command[command.index("--task") + 1] == "cs-ratings-semanal"
    # Compara COMPONENTES do caminho, não a string: "data\\ratings.json" fixava
    # o separador do Windows e o teste era impossível em qualquer runner POSIX.
    assert Path(command[command.index("--expected-artifact") + 1]).parts[-2:] == ("data", "ratings.json")
    assert command[command.index("--timeout") + 1] == "9000"


def test_entrypoint_help_never_starts_a_refresh() -> None:
    entrypoint = load_module("cs_entrypoint_help", "atualiza_semanal.py")
    with pytest.raises(SystemExit) as exited:
        entrypoint.main(["--help"])
    assert exited.value.code == 0


@pytest.mark.parametrize("failed_step", ["ingest", "ratings", "platt"])
def test_payload_propagates_each_step_failure_and_redacts(tmp_path: Path, monkeypatch, failed_step: str) -> None:
    payload = load_module(f"cs_payload_{failed_step}", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    payload.SENSITIVE_VALUES = ("fake_cs_secret_123",)

    def fake_run(command, **_):
        code = 1 if command[0] == failed_step else 0
        return SimpleNamespace(returncode=code, stdout="token=fake_cs_secret_123", stderr="token=fake_cs_secret_123")

    monkeypatch.setattr(payload, "build_steps", lambda _corte: [(name, [name], 1) for name in ("ingest", "ratings", "platt")])
    monkeypatch.setattr(payload.subprocess, "run", fake_run)
    assert payload.main() == 1
    contents = payload.LOG.read_text(encoding="utf-8")
    assert "fake_cs_secret_123" not in contents and "[REDACTED]" in contents


def test_payload_timeout_is_failure(tmp_path: Path, monkeypatch) -> None:
    payload = load_module("cs_payload_timeout", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    monkeypatch.setattr(payload, "build_steps", lambda _corte: [("ingest", ["ingest"], 1)])
    monkeypatch.setattr(payload.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(payload.subprocess.TimeoutExpired("ingest", 1)))
    assert payload.main() == 1
    assert "TIMEOUT" in payload.LOG.read_text(encoding="utf-8")


def test_payload_success_is_zero(tmp_path: Path, monkeypatch) -> None:
    payload = load_module("cs_payload_success", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    monkeypatch.setattr(payload, "build_steps", lambda _corte: [("ingest", ["ingest"], 1)])
    monkeypatch.setattr(payload.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    assert payload.main() == 0
