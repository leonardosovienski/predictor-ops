from __future__ import annotations

import base64
import csv
import hashlib
import json
import subprocess
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any


class ProvenanceError(RuntimeError):
    """Package identity could not be verified safely."""


def _verify_wheel() -> dict[str, Any]:
    try:
        dist = distribution("predictor-ops")
    except PackageNotFoundError as exc:
        raise ProvenanceError("predictor-ops distribution metadata is unavailable") from exc
    files = dist.files or []
    direct_url = next((item for item in files if item.name == "direct_url.json"), None)
    if direct_url is not None:
        try:
            direct = json.loads(Path(str(dist.locate_file(direct_url))).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProvenanceError("editable-install identity cannot be read") from exc
        if direct.get("dir_info", {}).get("editable"):
            raise ProvenanceError("editable installation is not a verifiable release artifact")
    record = next((item for item in files if item.name == "RECORD"), None)
    if record is None:
        raise ProvenanceError("installed distribution RECORD is unavailable")
    record_path = Path(str(dist.locate_file(record)))
    verified = 0
    try:
        rows = csv.reader(record_path.read_text(encoding="utf-8").splitlines())
        for relative, digest_spec, size_spec in rows:
            if not digest_spec:
                continue
            algorithm, encoded = digest_spec.split("=", 1)
            if algorithm != "sha256":
                raise ProvenanceError(f"unsupported RECORD hash: {algorithm}")
            path = Path(str(dist.locate_file(relative)))
            content = path.read_bytes()
            expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            if hashlib.sha256(content).digest() != expected or (size_spec and len(content) != int(size_spec)):
                raise ProvenanceError(f"installed package file failed verification: {relative}")
            verified += 1
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ProvenanceError):
            raise
        raise ProvenanceError(f"installed RECORD cannot be verified: {exc}") from exc
    if not verified:
        raise ProvenanceError("installed RECORD contains no verifiable files")
    return {"kind": "wheel", "version": dist.version, "verified_files": verified, "identity_status": "VALIDATED"}


def _source_identity(root: Path) -> dict[str, Any]:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    if result.returncode or not result.stdout.strip():
        raise ProvenanceError("source commit is unavailable")
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    if status.returncode:
        raise ProvenanceError("source worktree state is unavailable")
    clean = not status.stdout.strip()
    return {
        "kind": "source",
        "commit": result.stdout.strip(),
        "worktree_clean": clean,
        "identity_status": "VALIDATED" if clean else "DIRTY",
    }


def collect_provenance(*, strict: bool, source_root: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    candidates = []
    if source_root is not None:
        candidates.append(lambda: _source_identity(source_root))
    candidates.append(_verify_wheel)
    for candidate in candidates:
        try:
            value = candidate()
            if strict and value["identity_status"] != "VALIDATED":
                raise ProvenanceError("provenance identity is not validated")
            value["mode"] = "strict" if strict else "permissive"
            return value
        except ProvenanceError as exc:
            errors.append(str(exc))
    if strict:
        raise ProvenanceError("; ".join(errors))
    return {"kind": "unverified", "identity_status": "UNVERIFIED", "mode": "permissive", "errors": errors}


def safe_serialize(value: dict[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ProvenanceError("provenance is not JSON serializable") from exc
