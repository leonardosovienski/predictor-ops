"""Guarda-corpo para o split-brain de import flat vs. package (achado do
audit de provenance, rodada "tools/" 2026-07-17).

`core_provenance.py`, `operational_runner.py` e `release_manifest.py` tentam
`import tools.X` primeiro e caem para `import X` (flat) se o pacote não
estiver no sys.path. Confirmado por reprodução direta: `import tools.core_provenance`
e `import core_provenance` no mesmo processo criam DOIS objetos de módulo
distintos (`is` → False), cada um com sua própria cópia de qualquer estado de
módulo. Hoje isso é inofensivo porque nenhum módulo de tools/ mantém estado
mutável em nível de módulo (cache, flag "avisado uma vez", contador). Este
teste é o tripwire: se um módulo futuro adicionar esse tipo de estado, ele
precisa passar aqui — o teste falha e força quem escreveu o código a decidir
conscientemente se o split-brain importa para aquele estado específico, em
vez de a divergência aparecer como um bug silencioso meses depois.

Não migra nada, não remove o modo flat (isso quebraria os próprios testes
deste repositório, que importam flat — ver conftest/sys.path.insert em cada
arquivo de teste). Só documenta e trava a garantia atual.
"""
from __future__ import annotations

import ast
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]

# Módulos com o padrão de fallback duplo (package primeiro, flat como except).
_DUAL_IMPORT_MODULES = ("core_provenance", "operational_runner", "release_manifest")


def _has_module_level_global_statement(source: str) -> bool:
    """True se alguma função no módulo declara `global <nome>` — o sinal de
    estado mutável em nível de módulo que o split-brain poderia divergir."""
    tree = ast.parse(source)
    return any(isinstance(node, ast.Global) for node in ast.walk(tree))


def test_modulos_com_fallback_flat_package_nao_tem_estado_mutavel_de_modulo():
    offenders = []
    for name in _DUAL_IMPORT_MODULES:
        source = (TOOLS_ROOT / f"{name}.py").read_text(encoding="utf-8")
        if _has_module_level_global_statement(source):
            offenders.append(name)
    assert offenders == [], (
        f"{offenders} agora tem `global` (estado mutável de módulo) e também "
        "faz fallback flat/package — isso pode divergir silenciosamente entre "
        "as duas identidades de módulo no mesmo processo. Ver docstring deste "
        "arquivo antes de prosseguir."
    )


def test_import_duplo_flat_e_package_no_mesmo_processo_cria_objetos_distintos():
    # Confirma o fato estrutural em si (não é um bug, é a premissa que os
    # outros dois testes deste arquivo dependem): comprova que a condição
    # realmente existe, em vez de o guarda-corpo acima ficar sem lastro.
    import sys
    sys.path.insert(0, str(TOOLS_ROOT))
    sys.path.insert(0, str(TOOLS_ROOT.parent))
    try:
        import core_provenance as flat
        import tools.core_provenance as package
        assert flat is not package
        assert flat.__name__ != package.__name__
    finally:
        sys.modules.pop("core_provenance", None)
        sys.modules.pop("tools.core_provenance", None)


def test_readme_documenta_modo_de_execucao_suportado():
    readme = (TOOLS_ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m tools." in readme or "from tools import" in readme, (
        "README.md deve documentar explicitamente que o modo de execução "
        "suportado para consumidores externos é via pacote "
        "(`from tools import X` / `python -m tools.X`), não o import flat "
        "usado internamente pelos próprios testes de tools/."
    )


def test_api_publica_documentada_no_readme_e_importavel_via_pacote():
    # Espelha exatamente a tabela "Public API" do README — se um símbolo for
    # removido/renomeado ali, este teste quebra antes de qualquer consumidor
    # real notar em produção.
    from tools.operational_runner import write_heartbeat, run, main  # noqa: F401
    from tools.secret_redaction import (  # noqa: F401
        collect_sensitive_values, safe_redact_text, safe_redact_mapping,
    )
    from tools.tools_provenance import (  # noqa: F401
        collect_tools_provenance, ToolsProvenanceError,
    )
