"""Os `.ps1` do tools precisam ser ASCII puro, como nos demais projetos.

cs, lol, brasileirao, f1 e cripto ja checam isto no `scripts/ci_check.py`
("incidente V3.3.2"): PowerShell lido com a codepage errada transforma acento
em byte invalido e o script quebra em runtime, longe de onde foi escrito.

O `tools/` — a camada que instala e envelopa TODAS as tarefas agendadas do
ecossistema — era o unico sem essa barreira, e ja estava violando: o
`monitor_predictor_gates.ps1` carregava 6 bytes nao-ASCII numa mensagem de
`throw`, ou seja, exatamente no caminho de erro, que e o que menos se testa.
Encontrado em 2026-07-26 por varredura, nao por falha.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", sorted(ROOT.glob("*.ps1")), ids=lambda p: p.name)
def test_powershell_script_is_pure_ascii(script: Path) -> None:
    data = script.read_bytes()
    offenders = [(i, data[i]) for i in range(len(data)) if data[i] > 127]
    assert not offenders, (
        f"{script.name}: {len(offenders)} byte(s) nao-ASCII, primeiro no offset "
        f"{offenders[0][0]} (0x{offenders[0][1]:02x}). Use ASCII: 'nao' em vez "
        f"de 'não', '-' em vez de travessao."
    )


def test_there_is_at_least_one_script_to_check() -> None:
    # Sem isto, apagar todos os .ps1 (ou mudar o layout) faria a parametrizacao
    # ficar vazia e a barreira passaria a "verde" sem verificar nada.
    assert list(ROOT.glob("*.ps1")), "nenhum .ps1 encontrado — barreira vazia"
