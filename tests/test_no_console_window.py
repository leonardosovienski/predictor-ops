import ast
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parent.parent
INTERACTIVE_ONLY = {"tools_prompt.py"}

def _spawn_calls(tree: ast.AST) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute) and target.attr in {"run", "Popen"}:
                value = target.value
                if isinstance(value, ast.Name) and value.id == "subprocess":
                    found.append(node)
    return found

def _modules() -> list[Path]:
    return sorted(p for p in ROOT.glob("*.py") if p.name not in INTERACTIVE_ONLY)

def _sets_creationflags_in_a_mapping(tree: ast.AST) -> bool:
    """O modulo monta as opcoes num dict e expande com `**`.
    `operational_runner` faz isso porque as opcoes diferem entre nt e posix.
    Nesse caso o `**` e legitimo, e quem garante a flag de verdade e o teste
    de execucao abaixo, nao a leitura sintatica.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value == "creationflags":
                return True
    return False

@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
def test_every_child_spawn_declares_creationflags(module: Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    mapping_ok = _sets_creationflags_in_a_mapping(tree)
    for call in _spawn_calls(tree):
        keywords = {kw.arg for kw in call.keywords}
        if "creationflags" in keywords:
            continue
        if None in keywords and mapping_ok:
            continue  # `**opcoes`, com creationflags atribuido no dict
        pytest.fail(
            f"{module.name}:{call.lineno} lanca processo sem creationflags — "
            "sob pythonw.exe isso abre janela de console na tela do dono"
        )

@pytest.mark.skipif(sys.platform != "win32", reason="Específico para Windows")
def test_runner_really_spawns_the_child_without_a_console(tmp_path: Path) -> None:
    """Verificacao de execucao, nao de leitura de fonte.
    A flag do runner mora dentro de um dict expandido com `**`, entao o teste
    sintatico acima nao a enxerga — foi assim que ele falhou na primeira versao.
    Aqui o Popen real e envolvido e as flags efetivas sao inspecionadas.
    """
    import subprocess as sp
    from tools import operational_runner as runner

    seen: dict[str, int] = {}
    original = sp.Popen

    def recording_popen(*args, **kwargs):
        seen["creationflags"] = kwargs.get("creationflags", 0)
        return original(*args, **kwargs)

    sp.Popen = recording_popen
    try:
        code = runner.main(
            [
                "run",
                "--task",
                "t",
                "--project",
                "p",
                "--cwd",
                str(tmp_path),
                "--log",
                str(tmp_path / "h.log"),
                "--heartbeat",
                str(tmp_path / "hb.json"),
                "--event-log",
                str(tmp_path / "e.jsonl"),
                "--provenance-mode",
                "permissive",
                "--",
                sys.executable,
                "-c",
                "print('ok')",
            ]
        )
    finally:
        sp.Popen = original

    assert code == 0
    flags = seen["creationflags"]
    assert flags & sp.CREATE_NO_WINDOW, "o filho abriria console visivel"
    # O grupo de processos precisa sobreviver junto: e ele que permite matar a
    # arvore no timeout. Trocar um pelo outro quebraria o encerramento.
    assert flags & sp.CREATE_NEW_PROCESS_GROUP
