"""Testes de orquestração para release_check.py — o único módulo de tools/
sem cobertura dedicada, apontado no relatório da rodada "tools/" 2026-07-17.

release_check.py é um script fino que encadeia 4 subprocessos: pytest no
workspace, git clone isolado, pytest no clone, e uma sonda de provenance
estrita no clone. Testamos o ORQUESTRADOR — sequência de chamadas, cwd de
cada uma, propagação de falha e código de saída — mockando subprocess.run
para não pagar o custo (nem a fragilidade) de rodar pytest recursivamente
dentro de cada teste.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_check


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class _FakeRuns:
    """Substitui subprocess.run: registra cada chamada e devolve a próxima
    resposta programada (índice 0 = pytest do workspace, 1 = git clone,
    2 = pytest do clone, 3 = sonda de provenance)."""

    def __init__(self, responses: list[subprocess.CompletedProcess]):
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def __call__(self, command, cwd=None, check=False, capture_output=False, text=False):
        self.calls.append({"command": list(command), "cwd": Path(cwd) if cwd else None})
        index = len(self.calls) - 1
        return self._responses[min(index, len(self._responses) - 1)]


PROVENANCE_OK = json.dumps({"tools_version": "1.3.0", "content_hash": "deadbeef"}, sort_keys=True)


def test_caminho_feliz_imprime_json_e_retorna_zero(monkeypatch, capsys):
    fake = _FakeRuns([_completed(0), _completed(0), _completed(0), _completed(0, stdout=PROVENANCE_OK)])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {
        "workspace_tests": "passed",
        "isolated_clone_tests": "passed",
        "clone_provenance": json.loads(PROVENANCE_OK),
    }


def test_ordem_e_cwd_das_quatro_etapas_sao_corretos(monkeypatch):
    fake = _FakeRuns([_completed(0), _completed(0), _completed(0), _completed(0, stdout=PROVENANCE_OK)])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 0
    assert len(fake.calls) == 4
    # 1) pytest do workspace roda em release_check.WORKSPACE (a raiz do repo pai)
    assert fake.calls[0]["command"][1:3] == ["-m", "pytest"]
    assert "tools/tests" in fake.calls[0]["command"]
    assert fake.calls[0]["cwd"] == release_check.WORKSPACE
    # 2) git clone roda em release_check.ROOT (clona o próprio tools/)
    assert fake.calls[1]["command"][:2] == ["git", "clone"]
    assert fake.calls[1]["cwd"] == release_check.ROOT
    # 3) pytest do clone e 4) sonda de provenance rodam ambos na raiz do clone
    #    isolado (não em ROOT nem em WORKSPACE) — é o ponto central do teste:
    #    a validação estrita deve acontecer numa cópia byte-a-byte, não no
    #    checkout de desenvolvimento.
    assert fake.calls[2]["cwd"] not in (release_check.ROOT, release_check.WORKSPACE)
    assert fake.calls[2]["cwd"] == fake.calls[3]["cwd"]


def test_falha_no_pytest_do_workspace_aborta_e_nao_chega_a_clonar(monkeypatch, capsys):
    fake = _FakeRuns([_completed(1)])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 1
    assert len(fake.calls) == 1  # nunca chegou ao git clone
    err = capsys.readouterr().err
    assert "release verification failed" in err
    assert "1" in err  # returncode do comando que falhou aparece na mensagem


def test_falha_no_git_clone_e_reportada_com_clareza(monkeypatch, capsys):
    fake = _FakeRuns([_completed(0), _completed(128)])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 1
    assert len(fake.calls) == 2
    assert "128" in capsys.readouterr().err


def test_falha_no_pytest_do_clone_isolado_e_reportada(monkeypatch, capsys):
    fake = _FakeRuns([_completed(0), _completed(0), _completed(1)])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 1
    assert len(fake.calls) == 3


def test_sonda_de_provenance_com_returncode_nao_zero_usa_stderr(monkeypatch, capsys):
    fake = _FakeRuns([_completed(0), _completed(0), _completed(0),
                      _completed(2, stderr="ToolsProvenanceError: dirty checkout")])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 1
    assert "dirty checkout" in capsys.readouterr().err


def test_sonda_de_provenance_sem_stderr_ainda_da_mensagem_nao_vazia(monkeypatch, capsys):
    # probe.stderr vazio: o código cai no fallback "strict provenance
    # validation failed in clone" em vez de imprimir uma mensagem vazia.
    fake = _FakeRuns([_completed(0), _completed(0), _completed(0), _completed(3, stderr="")])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 1
    err = capsys.readouterr().err
    assert "strict provenance validation failed in clone" in err


def test_sonda_retorna_json_invalido_nao_crasha_com_traceback(monkeypatch, capsys):
    # probe.returncode == 0 mas stdout não é JSON válido — json.JSONDecodeError
    # está explicitamente capturada por main(); confirma que não escapa.
    fake = _FakeRuns([_completed(0), _completed(0), _completed(0),
                      _completed(0, stdout="isto nao e json")])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    assert release_check.main() == 1
    err = capsys.readouterr().err
    assert "release verification failed" in err
    assert "Traceback" not in err


def test_raiz_e_workspace_sao_derivados_do_arquivo_nao_do_cwd(monkeypatch, tmp_path):
    # "Execução fora da raiz": ROOT/WORKSPACE vêm de Path(__file__), então
    # trocar o cwd do processo (sem trocar __file__) não muda para onde os
    # subprocessos são direcionados.
    monkeypatch.chdir(tmp_path)
    assert release_check.ROOT == Path(release_check.__file__).resolve().parent
    assert release_check.WORKSPACE == release_check.ROOT.parent


def test_saida_de_sucesso_e_json_valido_de_uma_linha_para_consumo_automatizado(monkeypatch, capsys):
    fake = _FakeRuns([_completed(0), _completed(0), _completed(0), _completed(0, stdout=PROVENANCE_OK)])
    monkeypatch.setattr(release_check.subprocess, "run", fake)
    release_check.main()
    out = capsys.readouterr().out
    assert out.count("\n") == 1  # uma linha, terminada em \n — grep/jq-friendly
    json.loads(out)  # não levanta
