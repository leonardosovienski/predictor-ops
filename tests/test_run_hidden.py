"""O lancador sem janela precisa devolver o exit code do filho, sempre.

O `predictor-gate-monitor` sai com 1 quando ha tarefa degradada e o
`monitor_task_health.ps1` le esse `LastTaskResult`. Um lancador que engolisse
o codigo (o comportamento natural de `WScript.Shell.Run(..., False)`, a
alternativa que foi descartada) transformaria os dois monitores em decoracao
sem quebrar teste nenhum.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from tools import run_hidden


def test_propagates_child_success() -> None:
    assert run_hidden.main([sys.executable, "-c", "raise SystemExit(0)"]) == 0


@pytest.mark.parametrize("code", [1, 3, 10, 124])
def test_propagates_every_child_exit_code(code: int) -> None:
    # 1 = degradado (gate monitor), 10 = PARTIAL (payload do lol),
    # 124 = timeout (operational_runner). Nenhum pode virar 0.
    assert run_hidden.main([sys.executable, "-c", f"raise SystemExit({code})"]) == code


def test_missing_command_is_configuration_error() -> None:
    assert run_hidden.main([]) == run_hidden.CONFIGURATION_ERROR


def test_unlaunchable_command_is_configuration_error_not_crash() -> None:
    assert run_hidden.main(["executavel-que-nao-existe-em-lugar-nenhum"]) == \
        run_hidden.CONFIGURATION_ERROR


def test_report_survives_absent_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sob pythonw.exe nao ha console: sys.stderr e None. Um print direto
    # levantaria AttributeError e trocaria o exit code por um traceback.
    monkeypatch.setattr(sys, "stderr", None)
    assert run_hidden.main([]) == run_hidden.CONFIGURATION_ERROR


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW e do Windows")
def test_child_is_created_without_a_window(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_hidden.subprocess, "run", fake_run)
    run_hidden.main(["powershell.exe", "-File", "x.ps1"])
    assert seen["creationflags"] == run_hidden.CREATE_NO_WINDOW
    assert seen["command"] == ["powershell.exe", "-File", "x.ps1"]


def test_module_imports_no_network_and_no_domain_project() -> None:
    import inspect

    source = inspect.getsource(run_hidden)
    for forbidden in ("requests", "urllib", "httpx", "socket", "brasileirao",
                      "cs_predictor", "lol_predictor", "f1_predictor"):
        assert forbidden not in source.lower().replace("-", "_")
