"""Identity and release provenance for the workspace ``tools`` repository.

This module is intentionally stdlib-only.  It validates the release manifest
against the files actually used by the runner, so an operational record never
claims a release identity that cannot be reproduced locally.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

# `pythonw.exe` — o executavel de TODA tarefa agendada deste ecossistema — nao
# tem console. Um processo de CONSOLE lancado a partir dele ganha um console
# PROPRIO E VISIVEL: janela preta piscando na tela do dono. Este modulo chama
# `git` uma vez por arquivo rastreado em `content_hash` (35 hoje), mais
# rev-parse, status e ls-files: ~38 janelas por invocacao do runner, de hora em
# hora. CREATE_NO_WINDOW impede sem esconder nada — toda saida aqui ja e
# capturada. Vale 0 fora do Windows, onde o conceito nao existe.
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

MANIFEST_NAME = "TOOLS_MANIFEST.json"
SCHEMA_VERSION = "1.0"
HASH_ALGORITHM = "sha256-path-nul-content-nul-v1"
HASH_EXCLUDED = frozenset({"VERSION", MANIFEST_NAME})


class ToolsProvenanceError(RuntimeError):
    """The local tools release cannot be identified safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_tools_root() -> Path:
    return Path(__file__).resolve().parent


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], text=True,
                            capture_output=True, check=False,
                            creationflags=NO_WINDOW)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ToolsProvenanceError(detail)
    return result.stdout


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            check=False, creationflags=NO_WINDOW)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or "git command failed"
        raise ToolsProvenanceError(detail)
    return result.stdout


def _tracked_files(root: Path) -> list[str]:
    # -z: NUL-delimited output AND disables filename quoting — plain
    # `git ls-files` octal-escapes any non-ASCII path (e.g. "\303\261" for
    # "ñ"), which silently broke content_hash/build_manifest for any
    # tracked file with a non-ASCII name (the escaped string never resolves
    # to a real path via root / relative).
    raw = _git_bytes(root, "ls-files", "-z")
    files = [piece.decode("utf-8") for piece in raw.split(b"\0") if piece]
    files = [f for f in files if f not in HASH_EXCLUDED]
    if not files:
        raise ToolsProvenanceError("tools content set is empty")
    return sorted(files)


def content_hash(root: Path, files: list[str] | None = None) -> str:
    """Return the deterministic release fingerprint for tracked content.

    The byte stream is sorted UTF-8 relative path, NUL, raw Git-index blob,
    NUL. Git blobs make the release identity independent of checkout line-end
    normalization. Strict mode separately rejects a dirty worktree.
    ``VERSION`` and the release manifest are excluded to avoid a circular
    fingerprint; both remain separately validated release metadata.
    """
    digest = hashlib.sha256()
    for relative in files if files is not None else _tracked_files(root):
        if not (root / relative).is_file():
            raise ToolsProvenanceError(f"tracked content file is missing: {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_git_bytes(root, "show", f":{relative}"))
        digest.update(b"\0")
    return digest.hexdigest()


def _manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise ToolsProvenanceError(f"{MANIFEST_NAME} is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolsProvenanceError(f"invalid {MANIFEST_NAME}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolsProvenanceError(f"invalid {MANIFEST_NAME}: object required")
    return value


def collect_tools_provenance(root: Path | None = None, *, strict: bool = True) -> dict[str, Any]:
    """Return validated runtime provenance for the local tools checkout.

    Strict mode rejects a dirty checkout and a manifest/content mismatch.
    Explicit permissive mode preserves the release fingerprint and marks the
    checkout dirty; it is for compatibility diagnostics, never the default.
    """
    root = (root or default_tools_root()).resolve()
    version_file = root / "VERSION"
    if not version_file.is_file():
        raise ToolsProvenanceError("VERSION is missing")
    version = version_file.read_text(encoding="utf-8").strip()
    if not version:
        raise ToolsProvenanceError("VERSION is empty")
    try:
        commit = _git(root, "rev-parse", "HEAD").strip()
        clean = not _git(root, "status", "--porcelain").strip()
        manifest = _manifest(root)
        files = _tracked_files(root)
    except ToolsProvenanceError as exc:
        raise ToolsProvenanceError(f"tools provenance unavailable: {exc}") from exc
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ToolsProvenanceError("manifest schema_version is unsupported")
    if manifest.get("tools_version") != version:
        raise ToolsProvenanceError("manifest tools_version differs from VERSION")
    if manifest.get("hash_algorithm") != HASH_ALGORITHM:
        raise ToolsProvenanceError("manifest hash_algorithm is unsupported")
    if manifest.get("excluded_files") != sorted(HASH_EXCLUDED):
        raise ToolsProvenanceError("manifest excluded_files differs from contract")
    if manifest.get("included_files") != files:
        raise ToolsProvenanceError("manifest included_files differs from tracked content")
    computed = content_hash(root, files)
    expected = manifest.get("content_hash")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ToolsProvenanceError("manifest content_hash is invalid")
    if strict and not clean:
        raise ToolsProvenanceError("tools working tree is dirty in strict provenance mode")
    if strict and computed != expected:
        raise ToolsProvenanceError("tools content_hash diverges from release manifest")
    return {
        "version": version,
        "commit": commit,
        "content_hash": computed,
        "worktree_clean": clean,
        "generated_at_utc": utc_now(),
    }
