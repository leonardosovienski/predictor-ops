from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_manifest as generator
import tools_provenance as provenance


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True)


def _release_repo(tmp_path: Path, *, name: str = "tools") -> Path:
    """Git repo com VERSION + payload rastreado, SEM manifesto ainda —
    espelha o estado real que motivou esta onda: conteúdo commitado, mas
    TOOLS_MANIFEST.json desatualizado ou ausente."""
    root = tmp_path / name
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Tools Tests")
    (root / "VERSION").write_text("1.1.0\n", encoding="utf-8")
    (root / "payload.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_payload.py").write_text("def test_x(): assert True\n",
                                                     encoding="utf-8")
    _git(root, "add", "VERSION", "payload.py", "tests/test_payload.py")
    _git(root, "commit", "-m", "initial payload")
    return root


def _commit_manifest(root: Path, manifest: dict) -> None:
    (root / provenance.MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "manifest")


# ---------------------------------------------------------------------------
# 1. manifesto válido passa no check
# ---------------------------------------------------------------------------
def test_valid_manifest_passes_check(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    assert generator.cmd_write(root) == 0
    assert generator.cmd_check(root) == 0


# ---------------------------------------------------------------------------
# 2. arquivo rastreado alterado produz mismatch
# ---------------------------------------------------------------------------
def test_changed_tracked_file_produces_mismatch(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)
    (root / "payload.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(root, "add", "payload.py")
    _git(root, "commit", "-m", "change payload")
    assert generator.cmd_check(root) == 1


# ---------------------------------------------------------------------------
# 3. --write atualiza apenas TOOLS_MANIFEST.json
# ---------------------------------------------------------------------------
def test_write_touches_only_the_manifest_file(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*")
             if p.is_file() and ".git" not in p.parts and p.name != provenance.MANIFEST_NAME}
    generator.cmd_write(root)
    after = {p: p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts and p.name != provenance.MANIFEST_NAME}
    assert before == after
    assert (root / provenance.MANIFEST_NAME).is_file()


def test_write_refuses_when_new_untracked_payload_file_is_present(tmp_path: Path) -> None:
    # Regressão (auditoria hostil 2026-07-17, também vivida de verdade na
    # Onda 3A desta reintegração): --write ANTES de `git add` de um arquivo
    # novo calculava o manifesto sobre o ÍNDICE do Git (não o working tree) e
    # OMITIA o arquivo novo em silêncio, exit 0. Agora recusa com exit 2 e
    # não escreve nada, em vez de gerar um manifesto incompleto sem avisar.
    root = _release_repo(tmp_path)
    (root / "novo_nao_rastreado.py").write_text("X = 1\n", encoding="utf-8")
    before_exists = (root / provenance.MANIFEST_NAME).exists()
    assert generator.cmd_write(root) == 2
    assert (root / provenance.MANIFEST_NAME).exists() == before_exists  # nada escrito


def test_write_refuses_when_tracked_file_modified_but_not_staged(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    (root / "payload.py").write_text("VALUE = 999  # editado sem git add\n", encoding="utf-8")
    assert generator.cmd_write(root) == 2


def test_write_succeeds_after_git_add_of_pending_files(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    (root / "novo_nao_rastreado.py").write_text("X = 1\n", encoding="utf-8")
    assert generator.cmd_write(root) == 2  # ainda recusa
    _git(root, "add", "novo_nao_rastreado.py")
    assert generator.cmd_write(root) == 0  # agora aceita, arquivo no manifesto
    manifest = json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert "novo_nao_rastreado.py" in manifest["included_files"]


def test_write_does_not_block_on_rewriting_the_manifest_itself(tmp_path: Path) -> None:
    # A árvore ficar "suja" só por causa do TOOLS_MANIFEST.json recém-escrito
    # (ainda não commitado) é o fluxo normal write→inspecionar→commit — não
    # pode bloquear uma segunda escrita.
    root = _release_repo(tmp_path)
    assert generator.cmd_write(root) == 0
    assert generator.cmd_write(root) == 0  # segunda escrita, manifesto ainda não commitado


# ---------------------------------------------------------------------------
# 4. após --write, --check passa
# ---------------------------------------------------------------------------
def test_check_passes_after_write(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    assert generator.cmd_write(root) == 0
    assert generator.cmd_check(root) == 0


# ---------------------------------------------------------------------------
# 5. resultado determinístico para o mesmo conjunto de arquivos
# ---------------------------------------------------------------------------
def test_content_hash_is_deterministic(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    m1 = generator.build_manifest(root)
    m2 = generator.build_manifest(root)
    assert m1["content_hash"] == m2["content_hash"]


# ---------------------------------------------------------------------------
# 6. generated_at_utc não interfere no content_hash
# ---------------------------------------------------------------------------
def test_generated_at_utc_does_not_affect_content_hash(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)
    first = json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))
    generator.cmd_write(root)  # regrava sem mudar conteúdo rastreado
    second = json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert first["content_hash"] == second["content_hash"]


# ---------------------------------------------------------------------------
# 7. VERSION é excluído do hash, exatamente conforme o contrato documentado
# ---------------------------------------------------------------------------
def test_version_is_excluded_from_hash_per_documented_contract(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    before = generator.build_manifest(root)["content_hash"]
    (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    _git(root, "add", "VERSION")
    _git(root, "commit", "-m", "bump version only")
    after = generator.build_manifest(root)["content_hash"]
    assert before == after
    assert "VERSION" not in generator.build_manifest(root)["included_files"]
    assert "VERSION" in generator.build_manifest(root)["excluded_files"]


# ---------------------------------------------------------------------------
# 8. TOOLS_MANIFEST.json não causa autorreferência
# ---------------------------------------------------------------------------
def test_manifest_file_itself_is_excluded_from_its_own_hash(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)
    files = generator.build_manifest(root)["included_files"]
    assert provenance.MANIFEST_NAME not in files
    assert provenance.MANIFEST_NAME in generator.build_manifest(root)["excluded_files"]


# ---------------------------------------------------------------------------
# 9. ordem de enumeração do filesystem não altera o hash (lista sempre ordenada)
# ---------------------------------------------------------------------------
def test_included_files_are_stably_sorted(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    files = generator.build_manifest(root)["included_files"]
    assert files == sorted(files)


# ---------------------------------------------------------------------------
# 10. adição de arquivo rastreado altera o hash
# ---------------------------------------------------------------------------
def test_adding_tracked_file_changes_hash(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    before = generator.build_manifest(root)["content_hash"]
    (root / "extra.py").write_text("EXTRA = 1\n", encoding="utf-8")
    _git(root, "add", "extra.py")
    _git(root, "commit", "-m", "add file")
    after = generator.build_manifest(root)["content_hash"]
    assert before != after


# ---------------------------------------------------------------------------
# 11. remoção de arquivo rastreado altera o hash
# ---------------------------------------------------------------------------
def test_removing_tracked_file_changes_hash(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    before = generator.build_manifest(root)["content_hash"]
    _git(root, "rm", "tests/test_payload.py")
    _git(root, "commit", "-m", "remove file")
    after = generator.build_manifest(root)["content_hash"]
    assert before != after


# ---------------------------------------------------------------------------
# 12. arquivo excluído não altera o hash (coberto também pelo teste 7, aqui
#     cobrindo explicitamente o próprio manifesto sendo reescrito)
# ---------------------------------------------------------------------------
def test_rewriting_excluded_manifest_file_does_not_change_hash(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)
    before = generator.build_manifest(root)["content_hash"]
    # regrava o manifesto com generated_at_utc diferente + commita
    stale = json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))
    stale["generated_at_utc"] = "2000-01-01T00:00:00Z"
    (root / provenance.MANIFEST_NAME).write_text(json.dumps(stale), encoding="utf-8")
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "touch manifest only")
    after = generator.build_manifest(root)["content_hash"]
    assert before == after


# ---------------------------------------------------------------------------
# 13. target/diretório inválido falha sem escrita
# ---------------------------------------------------------------------------
def test_invalid_root_fails_without_writing(tmp_path: Path) -> None:
    fake = tmp_path / "does-not-exist"
    assert generator.cmd_write(fake) == 2
    assert not fake.exists()
    assert generator.cmd_check(fake) == 2


def test_root_without_git_fails_without_writing(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    assert generator.cmd_write(plain) == 2
    assert not (plain / provenance.MANIFEST_NAME).exists()


# ---------------------------------------------------------------------------
# 14. escrita atômica não deixa manifesto parcial em caso de erro simulado
# ---------------------------------------------------------------------------
def test_atomic_write_leaves_no_partial_manifest_on_simulated_failure(
    tmp_path: Path, monkeypatch
) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)  # manifesto válido existente
    original = json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))

    def _boom(*_args, **_kwargs):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(generator.os, "fsync", _boom)
    with pytest.raises(OSError):
        generator.cmd_write(root)
    # o manifesto original permanece intacto — nunca fica truncado/corrompido
    current = json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert current == original
    # nenhum arquivo temporário órfão fica para trás
    leftovers = [p for p in root.iterdir() if p.name.startswith(f".{provenance.MANIFEST_NAME}.")]
    assert leftovers == []


# ---------------------------------------------------------------------------
# 15. validador e gerador usam a mesma função de cálculo
# ---------------------------------------------------------------------------
def test_generator_and_validator_share_the_same_hash_function(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "commit generated manifest")
    validated = provenance.collect_tools_provenance(root, strict=True)
    expected = generator.build_manifest(root)
    assert validated["content_hash"] == expected["content_hash"]
    # prova estrutural, não só numérica: o gerador importa a MESMA função
    assert generator.content_hash is provenance.content_hash
    assert generator._tracked_files is provenance._tracked_files


# ---------------------------------------------------------------------------
# collect_tools_provenance(strict=True) falha antes do write, passa depois
# ---------------------------------------------------------------------------
def test_strict_provenance_fails_then_passes_after_regeneration(tmp_path: Path) -> None:
    root = _release_repo(tmp_path)
    generator.cmd_write(root)
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "commit generated manifest")
    (root / "payload.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(root, "add", "payload.py")
    _git(root, "commit", "-m", "drift")
    with pytest.raises(provenance.ToolsProvenanceError, match="diverges"):
        provenance.collect_tools_provenance(root, strict=True)
    assert generator.cmd_write(root) == 0
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "regenerate manifest")
    assert provenance.collect_tools_provenance(root, strict=True)["content_hash"] == \
        generator.build_manifest(root)["content_hash"]


# ---------------------------------------------------------------------------
# 16. nenhum projeto de domínio é importado / 17. nenhuma rede é necessária
# ---------------------------------------------------------------------------
def test_module_imports_no_domain_project_and_no_network() -> None:
    import inspect
    source = inspect.getsource(generator)
    for forbidden in ("requests", "urllib.request", "httpx", "socket",
                      "brasileirao", "cs_predictor", "lol_predictor",
                      "f1_predictor", "previsao_cripto"):
        assert forbidden not in source.lower().replace("-", "_")


# ---------------------------------------------------------------------------
# CLI smoke: --check e --write via main(argv)
# ---------------------------------------------------------------------------
def test_cli_check_and_write_via_main(tmp_path: Path, capsys) -> None:
    root = _release_repo(tmp_path)
    assert generator.main(["--check", "--root", str(root)]) == 2  # manifesto ainda não existe
    assert generator.main(["--write", "--root", str(root)]) == 0
    capsys.readouterr()
    assert generator.main(["--check", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_importable_as_tools_package_from_outside_tools_dir() -> None:
    # Regressão (auditoria hostil 2026-07-17): `from tools.release_manifest
    # import ...` de um consumidor externo levantava
    # `ModuleNotFoundError: No module named 'tools_provenance'`, porque o
    # módulo só tinha a forma de import "bare" (script standalone), sem o
    # fallback try/except que operational_runner.py já tem.
    import subprocess
    import sys
    workspace = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        [sys.executable, "-c", "from tools.release_manifest import build_manifest"],
        cwd=str(workspace), capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr
