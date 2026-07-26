"""Lancador sem janela para tarefas agendadas, preservando o exit code.

Por que existe: as tarefas do ecossistema que executam PowerShell
(`predictor-gate-monitor`, `predictor-task-health`) abriam uma janela de
console na tela do dono a cada disparo -- de 30 em 30 minutos, no caso do
monitor de gates. Como a acao agendada nao define WorkingDirectory, o console
abria em `C:\\Windows\\System32` e parecia que "o System32 abriu sozinho".

O `-WindowStyle Hidden` NAO resolve: ele e argumento do PowerShell, e quem cria
a janela e o console host do Windows, ANTES de o PowerShell comecar a rodar.

A correcao canonica seria `LogonType S4U` (roda sem area de trabalho), que e o
principal ja usado por `GarimpoV3Daily` e `cripto-watchdog-coleta`. Mas trocar
o principal de uma tarefa ja registrada exige elevacao -- `Set-ScheduledTask` e
`Register-ScheduledTask -Force` devolvem "Acesso negado" sem admin.

Este modulo e a correcao que NAO exige elevacao: `pythonw.exe` e do subsistema
GUI, entao nunca cria console; ele lanca o comando real com
`CREATE_NO_WINDOW` e propaga o exit code de volta. E o mesmo padrao ja usado
por todas as outras tarefas do ecossistema, que executam `pythonw.exe`.

Propagar o exit code e requisito, nao detalhe: o `predictor-gate-monitor` sai
com 1 quando algo esta degradado, e o `monitor_task_health.ps1` le exatamente
esse `LastTaskResult`. Um lancador que engolisse o codigo transformaria os dois
monitores em decoracao.

Uso:
    pythonw.exe run_hidden.py <executavel> [args...]

Stdlib-only, como o resto do `tools/`.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Sequence

# subprocess.CREATE_NO_WINDOW so existe no Windows; o literal mantem o modulo
# importavel (e testavel) em qualquer plataforma.
CREATE_NO_WINDOW = 0x08000000

CONFIGURATION_ERROR = 3


def _report(message: str) -> None:
    """Escreve em stderr quando ele existe.

    Sob `pythonw.exe` nao ha console e `sys.stderr` e None -- um `print`
    direto levantaria AttributeError e trocaria o exit code real por um
    traceback, que e exatamente o tipo de falha que este modulo existe para
    nao introduzir.
    """
    stream = getattr(sys, "stderr", None)
    if stream is not None:
        print(f"run_hidden: {message}", file=stream)


def main(argv: Sequence[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        _report("um comando e obrigatorio")
        return CONFIGURATION_ERROR
    creationflags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(command, creationflags=creationflags)
    except OSError as exc:
        _report(str(exc))
        return CONFIGURATION_ERROR
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
