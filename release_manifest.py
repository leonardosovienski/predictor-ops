"""Canonical generator for TOOLS_MANIFEST.json.

The release fingerprint algorithm has exactly one implementation:
``tools_provenance.content_hash`` / ``tools_provenance._tracked_files``. This
module never recomputes the hash independently — it imports and reuses that
same function, so the validator (``collect_tools_provenance``) and the
generator can never silently drift apart.

Usage (from the tools/ directory, or with --root pointing at a tools checkout):
    python release_manifest.py --check     # read-only: report drift, no write
    python release_manifest.py --write     # regenerate TOOLS_MANIFEST.json

--check performs no filesystem writes. --write touches only
TOOLS_MANIFEST.json, written atomically. Neither command runs Git commit,
push, or touches VERSION or any other tracked file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

try:  # Bare-script form first (matches this repo's own test/script convention
    # of putting tools/ itself on sys.path); falls back to the `tools.X`
    # package form for external consumers who only have the workspace root on
    # sys.path (found by adversarial audit 2026-07-17: this file used to only
    # have the bare form, breaking `from tools.release_manifest import ...`).
    from tools_provenance import (HASH_ALGORITHM, HASH_EXCLUDED, MANIFEST_NAME,
                                  SCHEMA_VERSION, ToolsProvenanceError,
                                  _git, _tracked_files, content_hash,
                                  default_tools_root, utc_now)
except ModuleNotFoundError:
    from tools.tools_provenance import (HASH_ALGORITHM, HASH_EXCLUDED, MANIFEST_NAME,  # type: ignore[no-redef]
                                        SCHEMA_VERSION, ToolsProvenanceError,
                                        _git, _tracked_files, content_hash,
                                        default_tools_root, utc_now)

# Keys that must be identical between the expected and the persisted manifest.
# generated_at_utc is deliberately excluded: it is metadata about WHEN the
# manifest was written, not part of the content fingerprint (content_hash
# itself never depends on it either — see tools_provenance.content_hash).
_STABLE_KEYS = ("schema_version", "tools_version", "content_hash",
                "hash_algorithm", "included_files", "excluded_files",
                "release_commit")


def _version(root: Path) -> str:
    version_file = root / "VERSION"
    if not version_file.is_file():
        raise ToolsProvenanceError("VERSION is missing")
    version = version_file.read_text(encoding="utf-8").strip()
    if not version:
        raise ToolsProvenanceError("VERSION is empty")
    return version


def build_manifest(root: Path) -> dict:
    """Pure, deterministic computation of every field except generated_at_utc.

    release_commit stays null: embedding the SHA of the commit that will
    contain this very manifest would be self-referential (documented in
    PROVENANCE.md); runtime provenance already records the actual commit."""
    files = _tracked_files(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "tools_version": _version(root),
        "content_hash": content_hash(root, files),
        "hash_algorithm": HASH_ALGORITHM,
        "included_files": files,
        "excluded_files": sorted(HASH_EXCLUDED),
        "release_commit": None,
    }


def cmd_check(root: Path | None = None) -> int:
    """Read-only: compare the persisted manifest against freshly computed
    content. Never writes. Returns 0 in sync, 1 on mismatch, 2 on error."""
    root = (root or default_tools_root()).resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        print(f"erro: {MANIFEST_NAME} não existe em {root}")
        return 2
    try:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"erro: {MANIFEST_NAME} inválido: {exc}")
        return 2
    if not isinstance(current, dict):
        print(f"erro: {MANIFEST_NAME} inválido: objeto esperado")
        return 2
    try:
        expected = build_manifest(root)
    except ToolsProvenanceError as exc:
        print(f"erro: não foi possível computar o manifesto esperado: {exc}")
        return 2
    if all(current.get(key) == expected[key] for key in _STABLE_KEYS):
        print(f"OK: {MANIFEST_NAME} em sincronia "
              f"(tools_version={expected['tools_version']}, "
              f"content_hash={expected['content_hash']}, "
              f"arquivos={len(expected['included_files'])})")
        return 0
    print(f"MISMATCH: {MANIFEST_NAME} não corresponde ao conteúdo rastreado atual")
    for key in _STABLE_KEYS:
        if current.get(key) != expected[key]:
            print(f"  difere: {key}")
    return 1


def cmd_write(root: Path | None = None) -> int:
    """Regenerate TOOLS_MANIFEST.json atomically. Touches no other file."""
    root = (root or default_tools_root()).resolve()
    manifest_path = root / MANIFEST_NAME
    try:
        # `git status --porcelain` reporta cada entrada como "XY caminho":
        # X = status no índice (staged), Y = status no working tree (não
        # staged). content_hash/_tracked_files leem do ÍNDICE (git show
        # :path) — um arquivo já staged (git add feito, "A " ou "M ") é
        # SEGURO, o índice já reflete o conteúdo pretendido. O problema real
        # é Y != ' ' (mudança no working tree que ainda NÃO foi staged) ou
        # "??" (novo, nem rastreado) — esses SIM ficam invisíveis para o
        # manifesto. O próprio TOOLS_MANIFEST.json é sempre excluído:
        # regravá-lo é exatamente o que --write faz, e ele ficar staged-mas-
        # não-commitado até o commit seguinte é o fluxo normal
        # (write → inspecionar → commit), não a ordem insegura que esta
        # checagem existe para pegar.
        status_lines = [ln for ln in _git(root, "status", "--porcelain").splitlines()
                        if ln.strip() and not ln[3:].strip().endswith(MANIFEST_NAME)
                        and (ln[:2] == "??" or ln[1] != " ")]
    except ToolsProvenanceError:
        status_lines = None  # não é um repo git (ou git indisponível): não é possível checar
    if status_lines:
        # Auditoria hostil 2026-07-17: rodar --write ANTES de `git add` de
        # arquivos novos/alterados fazia o manifesto ser calculado sobre o
        # ÍNDICE do Git (via content_hash/_tracked_files), não o working
        # tree — um arquivo novo era omitido em silêncio, exit 0, sem aviso
        # (incidente real desta mesma sessão, Onda 3A). Recusar de cara aqui
        # é estritamente melhor: sem isso, o erro só apareceria depois, no
        # --check ou no collect_tools_provenance(strict=True) de alguém
        # esperando MATCH.
        print("erro: há arquivos modificados/novos ainda NÃO staged (git add) "
              f"em {root} — content_hash é calculado sobre o ÍNDICE do Git, "
              "não o working tree, então --write ignoraria essas mudanças em "
              "silêncio. Rode `git add` nos arquivos pretendidos antes de "
              "--write (não precisa commitar ainda). Arquivos: "
              + "; ".join(ln.strip() for ln in status_lines))
        return 2
    try:
        payload = build_manifest(root)
    except ToolsProvenanceError as exc:
        print(f"erro: {exc}")
        return 2
    payload["generated_at_utc"] = utc_now()
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="",
                                         delete=False, dir=manifest_path.parent,
                                         prefix=f".{MANIFEST_NAME}.") as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, manifest_path)
    except BaseException:
        # Nunca deixar um arquivo temporário órfão para trás em caso de falha
        # a meio da escrita — o manifesto real (manifest_path) permanece
        # intocado até o os.replace bem-sucedido, este cleanup só cuida do
        # arquivo intermediário.
        if temporary is not None and temporary.exists():
            temporary.unlink()
        raise
    print(f"escrito: {MANIFEST_NAME} (tools_version={payload['tools_version']}, "
          f"content_hash={payload['content_hash']}, "
          f"arquivos={len(payload['included_files'])})")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(
        description="Canonical generator/validator for TOOLS_MANIFEST.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="read-only: report drift, do not write")
    group.add_argument("--write", action="store_true",
                       help="regenerate TOOLS_MANIFEST.json")
    parser.add_argument("--root", default=None,
                        help="tools/ root (defaults to this file's directory)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    try:
        return cmd_check(root) if args.check else cmd_write(root)
    except ToolsProvenanceError as exc:
        print(f"erro: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
