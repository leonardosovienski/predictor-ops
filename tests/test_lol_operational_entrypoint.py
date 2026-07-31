from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]

# `atualiza_semanal.py` do lol aborta no guard de proveniência
# (`runtime_manifest.ARTIFACTS`) se faltar qualquer um destes quatro artefatos
# operacionais — que nascem da ingestão do Oracle's Elixir e são gitignored.
#
# Por que NÃO existe um seed sintético para eles, como há no f1 e no
# brasileirao: `data/calibration.json` não é artefato inerte, é um INTERRUPTOR
# DE MODO. `src/model.py::_kills_calibration` cai no baseline global do
# config.yaml quando o arquivo está ausente, mas passa a EXIGIR `--kills-league`
# quando ele existe. Criar um calibration.json de mentira derruba 9 testes reais
# do próprio lol-predictor (test_model/test_predict) — verificado. Um fixture
# não pode mudar a semântica de produção para se acomodar.
_LOL_RUNTIME_ARTIFACTS = ("lol.db", "ratings.json", "calibration.json", "teams_lol.json")
requires_lol_runtime_data = pytest.mark.skipif(
    not all((ROOT / "lol-predictor" / "data" / name).is_file()
            for name in _LOL_RUNTIME_ARTIFACTS),
    reason="artefatos operacionais do lol-predictor ausentes (gitignored) e "
           "insintetizáveis: um calibration.json sintético muda o modo do modelo")


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "lol-predictor" / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@requires_lol_runtime_data
def test_entrypoint_uses_shared_operational_contract(monkeypatch) -> None:
    entrypoint = load_module("lol_entrypoint_contract", "atualiza_semanal.py")
    seen: list[list[str]] = []
    monkeypatch.setattr(entrypoint.subprocess, "run", lambda command, **_: seen.append(command) or SimpleNamespace(returncode=5))
    assert entrypoint.main([]) == 5
    command = seen[0]
    assert command[command.index("--task") + 1] == "lol-ratings-semanal"
    # Compara COMPONENTES do caminho, não a string: "data\\ratings.json" fixava
    # o separador do Windows e o teste era impossível em qualquer runner POSIX.
    assert Path(command[command.index("--expected-artifact") + 1]).parts[-2:] == ("data", "ratings.json")
    assert command[command.index("--timeout") + 1] == "9000"
    assert command[command.index("--partial-exit-code") + 1] == "10"


def test_entrypoint_help_never_starts_refresh() -> None:
    entrypoint = load_module("lol_entrypoint_help", "atualiza_semanal.py")
    with pytest.raises(SystemExit) as exited:
        entrypoint.main(["--help"])
    assert exited.value.code == 0


@pytest.mark.parametrize("failed_step", ["ingest", "ratings"])
def test_payload_propagates_step_failure_and_redacts(tmp_path: Path, monkeypatch, failed_step: str) -> None:
    payload = load_module(f"lol_payload_{failed_step}", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    payload.SENSITIVE_VALUES = ("fake_lol_secret_123",)
    monkeypatch.setattr(payload, "download_csv", lambda _year: True)
    monkeypatch.setattr(payload, "ratings_valid", lambda _started: True)

    def fake_run(command, **_):
        return SimpleNamespace(
            returncode=1 if command[0] == failed_step else 0,
            stdout="token=fake_lol_secret_123",
            stderr="token=fake_lol_secret_123",
        )

    monkeypatch.setattr(payload, "build_steps", lambda: [(name, [name], 1) for name in ("ingest", "ratings")])
    monkeypatch.setattr(payload.subprocess, "run", fake_run)
    assert payload.main() == 1
    contents = payload.LOG.read_text(encoding="utf-8")
    assert "fake_lol_secret_123" not in contents and "[REDACTED]" in contents


@requires_lol_runtime_data
def test_download_failure_with_fresh_artifact_is_partial(tmp_path: Path, monkeypatch) -> None:
    payload = load_module("lol_payload_partial", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    monkeypatch.setattr(payload, "download_csv", lambda _year: False)
    monkeypatch.setattr(payload, "ratings_valid", lambda _started: True)
    monkeypatch.setattr(payload, "build_steps", lambda: [("ingest", ["ingest"], 1)])
    monkeypatch.setattr(payload.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    assert payload.main() == payload.PARTIAL_EXIT


def test_payload_timeout_is_failure(tmp_path: Path, monkeypatch) -> None:
    payload = load_module("lol_payload_timeout", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    monkeypatch.setattr(payload, "download_csv", lambda _year: True)
    monkeypatch.setattr(payload, "ratings_valid", lambda _started: True)
    monkeypatch.setattr(payload, "build_steps", lambda: [("ingest", ["ingest"], 1)])
    monkeypatch.setattr(payload.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(payload.subprocess.TimeoutExpired("ingest", 1)))
    assert payload.main() == 1
    assert "TIMEOUT" in payload.LOG.read_text(encoding="utf-8")


def test_ratings_validation_requires_fresh_nonempty_numeric_mapping(tmp_path: Path, monkeypatch) -> None:
    payload = load_module("lol_payload_artifact", "atualiza_semanal_payload.py")
    payload.LOG = tmp_path / "refresh.log"
    monkeypatch.setattr(payload, "ROOT", tmp_path)
    path = tmp_path / "data" / "ratings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"team": 1500.0}), encoding="utf-8")
    assert payload.ratings_valid(time.time() - 1)
    path.write_text(json.dumps({"team": "not-a-rating"}), encoding="utf-8")
    assert not payload.ratings_valid(time.time() - 1)
