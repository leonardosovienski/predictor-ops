#!/usr/bin/env python3
"""Read-only byte auditor for vendored ``predictor_core`` copies.

This tool intentionally does not import, modify, synchronize, prune, or rewrite a
vendor.  It compares each vendor payload to the canonical source byte-for-byte and
uses normalized text only to explain a raw mismatch.

Exit codes:
  0 all vendors are IDENTICAL
  1 one or more vendors have payload drift/incomplete/extra files
  2 one or more manifests are absent or inconsistent
  3 an operational error prevented a comparison
  4 one or more requested consumers are not verifiable

When categories coexist, precedence is ERROR (3), NOT_VERIFIABLE (4),
MANIFEST_MISMATCH (2), then payload drift (1).  The report always retains each
consumer's individual status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MANIFEST_NAME = "CORE_MANIFEST.json"
NOT_PAYLOAD = {"sync_core.py", MANIFEST_NAME, "README.md", "CHANGELOG.md"}
EXCLUDE_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".claude",
    "tests",
    "docs",
}
EXIT_CODES = {
    "IDENTICAL": 0,
    "DRIFT": 1,
    "INCOMPLETE": 1,
    "EXTRA_FILES": 1,
    "MANIFEST_MISMATCH": 2,
    "ERROR": 3,
    "NOT_VERIFIABLE": 4,
}
EXIT_PRECEDENCE = ("ERROR", "NOT_VERIFIABLE", "MANIFEST_MISMATCH", "INCOMPLETE", "EXTRA_FILES", "DRIFT")


@dataclass(frozen=True)
class PayloadEntry:
    path: Path
    kind: str
    sha256: str | None
    error: str | None = None


def _kind(path: Path) -> str:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def _is_payload_path(relative: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in relative.parts):
        return False
    if len(relative.parts) == 1 and relative.name in NOT_PAYLOAD:
        return False
    return relative.suffix == ".py" or relative.name == "VERSION"


def payload_entries(root: Path) -> dict[str, PayloadEntry]:
    """Return payload entries keyed by canonical POSIX relative path.

    The selection mirrors ``predictor_core/sync_core.py``: recursive ``*.py`` plus
    ``VERSION``, excluding tooling, documentation, cache and tests.  A symlink is
    reported as a distinct file type; it is never silently dereferenced for the
    byte-comparison truth.
    """
    entries: dict[str, PayloadEntry] = {}
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root)
            if not _is_payload_path(relative):
                continue
            rel = relative.as_posix()
            try:
                kind = _kind(path)
                if kind != "file":
                    entries[rel] = PayloadEntry(path=path, kind=kind, sha256=None)
                else:
                    entries[rel] = PayloadEntry(
                        path=path,
                        kind=kind,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
            except OSError as exc:
                entries[rel] = PayloadEntry(path=path, kind="unreadable", sha256=None, error=str(exc))
    return dict(sorted(entries.items()))


def aggregate(entries: dict[str, PayloadEntry]) -> str | None:
    """Use the existing manifest aggregate formula only when all entries are files."""
    if any(entry.kind != "file" or entry.sha256 is None for entry in entries.values()):
        return None
    file_hashes = {name: entry.sha256 for name, entry in entries.items()}
    return hashlib.sha256(json.dumps(file_hashes, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _bom_name(data: bytes) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-bom"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return None


def _strip_bom(data: bytes) -> bytes:
    name = _bom_name(data)
    return data[3:] if name == "utf-8-bom" else data[2:] if name else data


def text_diagnostic(canonical: bytes, vendor: bytes) -> dict[str, str] | None:
    """Explain a raw mismatch without changing the primary byte comparison."""
    canonical_bom = _bom_name(canonical)
    vendor_bom = _bom_name(vendor)
    if _strip_bom(canonical) == _strip_bom(vendor) and canonical_bom != vendor_bom:
        return {"kind": "BOM_ONLY", "canonical_bom": str(canonical_bom), "vendor_bom": str(vendor_bom)}
    try:
        canonical_text = canonical.decode("utf-8-sig")
        vendor_text = vendor.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    normalized_canonical = canonical_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_vendor = vendor_text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized_canonical == normalized_vendor:
        if canonical_text != vendor_text:
            return {"kind": "NEWLINE_ONLY"}
        return {
            "kind": "TEXT_NORMALIZED_MATCH",
            "canonical_bom": str(canonical_bom),
            "vendor_bom": str(vendor_bom),
        }
    return None


def _read_manifest(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "manifest missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"manifest unreadable: {exc}"
    if not isinstance(value, dict) or not isinstance(value.get("files"), dict) or not isinstance(value.get("aggregate"), str):
        return None, "manifest has invalid schema"
    if not all(isinstance(name, str) and isinstance(digest, str) for name, digest in value["files"].items()):
        return None, "manifest files must map strings to strings"
    return value, None


def _manifest_issues(manifest: dict[str, Any] | None, actual: dict[str, PayloadEntry], expected: dict[str, PayloadEntry]) -> list[str]:
    if manifest is None:
        return ["manifest missing or invalid"]
    issues: list[str] = []
    actual_hashes = {name: entry.sha256 for name, entry in actual.items() if entry.kind == "file" and entry.sha256}
    declared_files = manifest["files"]
    declared_aggregate = manifest["aggregate"]
    if not isinstance(manifest.get("source_version"), str):
        issues.append("manifest source_version is missing or invalid")
    recomputed_declared = hashlib.sha256(json.dumps(declared_files, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    if declared_aggregate != recomputed_declared:
        issues.append("manifest aggregate does not match declared file hashes")
    if declared_files != actual_hashes:
        issues.append("manifest file hashes do not match vendor payload")
    expected_aggregate = aggregate(expected)
    if declared_aggregate != expected_aggregate:
        issues.append("manifest aggregate does not match canonical payload")
    return issues


def audit_vendor(consumer: str, vendor: Path, canonical: Path) -> dict[str, Any]:
    base: dict[str, Any] = {
        "consumer": consumer,
        "path": str(vendor),
        "status": "ERROR",
        "confidence": "high",
        "limitations": ["byte comparison does not prove which path runtime imports"],
    }
    if not canonical.is_dir():
        base.update(status="ERROR", confidence="low", limitations=["canonical directory is missing"])
        return base
    try:
        expected = payload_entries(canonical)
    except OSError as exc:
        base.update(status="ERROR", confidence="low", limitations=[f"canonical read error: {exc}"])
        return base
    base["canonical_file_count"] = len(expected)
    base["expected_aggregate"] = aggregate(expected)
    canonical_version = canonical / "VERSION"
    base["canonical_version"] = canonical_version.read_text(encoding="utf-8").strip() if canonical_version.is_file() else None
    if not vendor.is_dir():
        base.update(status="NOT_VERIFIABLE", confidence="high", limitations=["vendor directory is missing"])
        return base

    try:
        actual = payload_entries(vendor)
    except OSError as exc:
        base.update(status="ERROR", confidence="low", limitations=[f"vendor read error: {exc}"])
        return base
    manifest, manifest_error = _read_manifest(vendor / MANIFEST_NAME)
    base["observed_file_count"] = len(actual)
    base["observed_aggregate"] = aggregate(actual)
    version_path = vendor / "VERSION"
    try:
        base["declared_version"] = manifest.get("source_version") if manifest else None
        base["detected_version"] = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else None
    except (OSError, UnicodeDecodeError) as exc:
        base["detected_version"] = None
        base.setdefault("read_errors", []).append(str(exc))

    expected_names = set(expected)
    actual_names = set(actual)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    changed: list[dict[str, Any]] = []
    identical_files = 0
    errors: list[str] = []
    for name in sorted(expected_names & actual_names):
        left, right = expected[name], actual[name]
        if left.error or right.error:
            errors.append(f"{name}: {left.error or right.error}")
            continue
        if left.kind != right.kind:
            changed.append({"path": name, "kind": "TYPE_DIFFERENT", "canonical_type": left.kind, "vendor_type": right.kind})
            continue
        if left.kind != "file":
            changed.append({"path": name, "kind": "NON_REGULAR_PAYLOAD", "canonical_type": left.kind, "vendor_type": right.kind})
            continue
        if left.sha256 != right.sha256:
            detail: dict[str, Any] = {"path": name, "kind": "CONTENT_DIFFERENT", "canonical_sha256": left.sha256, "vendor_sha256": right.sha256}
            try:
                diagnostic = text_diagnostic(left.path.read_bytes(), right.path.read_bytes())
            except OSError as exc:
                errors.append(f"{name}: {exc}")
                diagnostic = None
            if diagnostic:
                detail["text_diagnostic"] = diagnostic
            changed.append(detail)
        else:
            identical_files += 1

    manifest_issues = _manifest_issues(manifest, actual, expected)
    if manifest_error:
        manifest_issues.insert(0, manifest_error)
    if base.get("declared_version") not in (None, base["canonical_version"]):
        manifest_issues.append("manifest source_version does not match canonical VERSION")
    status = "IDENTICAL"
    if errors:
        status = "ERROR"
    elif missing:
        status = "INCOMPLETE"
    elif extra:
        status = "EXTRA_FILES"
    elif changed:
        status = "DRIFT"
    elif manifest_issues:
        status = "MANIFEST_MISMATCH"
    elif base["detected_version"] != base["canonical_version"]:
        status = "DRIFT"
        changed.append({"path": "VERSION", "kind": "VERSION_DIFFERENT"})

    base.update(
        status=status,
        identical_files=identical_files,
        changed_files=changed,
        missing_files=missing,
        extra_files=extra,
        manifest_issues=manifest_issues,
        read_errors=errors + base.get("read_errors", []),
    )
    if status in {"ERROR", "NOT_VERIFIABLE"}:
        base["confidence"] = "low"
    elif status != "IDENTICAL":
        base["confidence"] = "high"
    return base


def discover_consumers(workspace: Path) -> list[tuple[str, Path]]:
    if not workspace.is_dir():
        return []
    found = []
    for path in sorted(workspace.iterdir(), key=lambda item: item.name):
        vendor = path / "vendor" / "predictor_core"
        if path.is_dir() and vendor.is_dir():
            found.append((path.name, vendor))
    return found


def exit_code(results: Iterable[dict[str, Any]]) -> int:
    statuses = {result["status"] for result in results}
    for status in EXIT_PRECEDENCE:
        if status in statuses:
            return EXIT_CODES[status]
    return 0


def report(workspace: Path, canonical: Path, requested_consumers: list[str] | None = None) -> dict[str, Any]:
    if requested_consumers:
        consumers = [(name, workspace / name / "vendor" / "predictor_core") for name in sorted(set(requested_consumers))]
    else:
        consumers = discover_consumers(workspace)
    results = [audit_vendor(name, vendor, canonical) for name, vendor in consumers]
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {
        "canonical_path": str(canonical),
        "workspace_path": str(workspace),
        "payload_rules": {
            "included": ["**/*.py", "VERSION"],
            "excluded_directories": sorted(EXCLUDE_DIRS),
            "excluded_root_files": sorted(NOT_PAYLOAD),
            "raw_bytes_are_primary": True,
        },
        "consumers": results,
        "summary": {"consumer_count": len(results), "statuses": dict(sorted(counts.items()))},
        "exit_code": exit_code(results),
    }


def _human(report_data: dict[str, Any]) -> str:
    lines = [
        "predictor_core vendor byte audit (read-only)",
        f"canonical: {report_data['canonical_path']}",
        f"consumers: {report_data['summary']['consumer_count']}",
    ]
    for result in report_data["consumers"]:
        lines.append(
            f"{result['consumer']}: {result['status']} "
            f"files={result.get('observed_file_count', 0)}/{result.get('canonical_file_count', 0)} "
            f"identical={result.get('identical_files', 0)} changed={len(result.get('changed_files', []))} "
            f"missing={len(result.get('missing_files', []))} extra={len(result.get('extra_files', []))}"
        )
        for key in ("changed_files", "missing_files", "extra_files", "manifest_issues", "read_errors"):
            for item in result.get(key, []):
                lines.append(f"  {key}: {json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else item}")
    lines.append(f"exit_code: {report_data['exit_code']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only byte audit for vendored predictor_core copies")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--canonical", type=Path, default=None)
    parser.add_argument("--consumer", action="append", help="consumer directory name; repeatable")
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON to stdout")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        # Auditoria hostil 2026-07-17: sem esta checagem, discover_consumers()
        # devolvia [] silenciosamente para um workspace inexistente/typo, e o
        # relatório saía com consumer_count=0 e exit_code=0 — "tudo
        # verificado", quando na verdade a auditoria nem chegou a rodar. Um
        # pipeline de CI/monitoramento que só olha o exit code veria sucesso.
        print(f"erro: --workspace não é um diretório: {workspace}", file=sys.stderr)
        return 2
    canonical = (args.canonical or workspace / "predictor_core").resolve()
    data = report(workspace, canonical, args.consumer)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(_human(data))
    return data["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
