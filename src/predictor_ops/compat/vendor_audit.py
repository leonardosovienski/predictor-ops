from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _files(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        raise ValueError(f"audit root is not a directory: {root.name}")
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, path in sorted(_files(root).items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def audit_vendor(canonical: Path, vendor: Path) -> dict[str, Any]:
    expected, actual = _files(canonical), _files(vendor)
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed: list[str] = []
    diagnostics: dict[str, list[str]] = {}
    for relative in sorted(expected.keys() & actual.keys()):
        left, right = expected[relative].read_bytes(), actual[relative].read_bytes()
        if left != right:
            changed.append(relative)
            details = []
            if left.lstrip(b"\xef\xbb\xbf") == right.lstrip(b"\xef\xbb\xbf"):
                details.append("BOM_ONLY")
            if left.replace(b"\r\n", b"\n") == right.replace(b"\r\n", b"\n"):
                details.append("NEWLINE_ONLY")
            diagnostics[relative] = details or ["BYTE_MISMATCH"]
    status = "IDENTICAL" if not (missing or extra or changed) else "MISMATCH"
    return {
        "status": status,
        "canonical_digest": tree_digest(canonical),
        "vendor_digest": tree_digest(vendor),
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "diagnostics": diagnostics,
    }
