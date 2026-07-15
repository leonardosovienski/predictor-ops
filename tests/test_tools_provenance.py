from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tools import tools_provenance as provenance


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def release_repo(tmp_path: Path) -> Path:
    root = tmp_path / "tools"
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Tools Tests")
    (root / "VERSION").write_text("1.1.0\n", encoding="utf-8")
    (root / "payload.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "VERSION", "payload.py")
    files = ["payload.py"]
    manifest = {
        "schema_version": "1.0", "tools_version": "1.1.0",
        "content_hash": provenance.content_hash(root, files),
        "hash_algorithm": provenance.HASH_ALGORITHM,
        "included_files": files, "excluded_files": sorted(provenance.HASH_EXCLUDED),
        "generated_at_utc": "2026-07-15T00:00:00Z", "release_commit": None,
    }
    (root / provenance.MANIFEST_NAME).write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "release")
    return root


def test_valid_provenance_has_real_commit_and_deterministic_hash(tmp_path: Path) -> None:
    root = release_repo(tmp_path)
    first = provenance.collect_tools_provenance(root)
    second = provenance.collect_tools_provenance(root)
    assert first["version"] == "1.1.0" and len(first["commit"]) == 40
    assert first["worktree_clean"] is True
    assert first["content_hash"] == second["content_hash"]


def test_clean_clone_reproduces_content_hash(tmp_path: Path) -> None:
    root = release_repo(tmp_path)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", str(root), str(clone)], check=True, capture_output=True, text=True)
    assert provenance.collect_tools_provenance(root)["content_hash"] == provenance.collect_tools_provenance(clone)["content_hash"]


def test_dirty_strict_fails_and_explicit_permissive_reports_real_state(tmp_path: Path) -> None:
    root = release_repo(tmp_path)
    (root / "payload.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(provenance.ToolsProvenanceError, match="dirty"):
        provenance.collect_tools_provenance(root, strict=True)
    observed = provenance.collect_tools_provenance(root, strict=False)
    assert observed["worktree_clean"] is False
    assert observed["content_hash"] != json.loads((root / provenance.MANIFEST_NAME).read_text(encoding="utf-8"))["content_hash"]


def test_missing_git_version_and_invalid_manifest_fail_closed(tmp_path: Path) -> None:
    no_git = tmp_path / "no-git"
    no_git.mkdir()
    (no_git / "VERSION").write_text("1.1.0\n", encoding="utf-8")
    with pytest.raises(provenance.ToolsProvenanceError):
        provenance.collect_tools_provenance(no_git)
    root = release_repo(tmp_path / "release")
    (root / "VERSION").unlink()
    with pytest.raises(provenance.ToolsProvenanceError, match="VERSION"):
        provenance.collect_tools_provenance(root)


def test_manifest_hash_divergence_and_invalid_schema_fail(tmp_path: Path) -> None:
    root = release_repo(tmp_path)
    manifest = root / provenance.MANIFEST_NAME
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["content_hash"] = "0" * 64
    manifest.write_text(json.dumps(value), encoding="utf-8")
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "bad manifest")
    with pytest.raises(provenance.ToolsProvenanceError, match="diverges"):
        provenance.collect_tools_provenance(root)
    value["schema_version"] = "broken"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    _git(root, "add", provenance.MANIFEST_NAME)
    _git(root, "commit", "-m", "bad schema")
    with pytest.raises(provenance.ToolsProvenanceError, match="schema"):
        provenance.collect_tools_provenance(root, strict=False)
