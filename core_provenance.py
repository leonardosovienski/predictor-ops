#!/usr/bin/env python3
"""Inspect and verify the runtime provenance of vendored ``predictor_core``.

The normal import path is untouched.  This tool is called explicitly (manually,
from CI, or by an opt-in entrypoint) and never writes, synchronizes, installs, or
changes ``sys.path`` in its parent process.

Exit codes: 0 MATCH; 1 provenance mismatch; 2 invalid configuration;
3 import/subprocess error; 4 incomplete/not verifiable.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from vendor_byte_audit import MANIFEST_NAME, aggregate, discover_consumers, payload_entries


EXIT_CODES = {
    "MATCH": 0,
    "PATH_MISMATCH": 1,
    "VERSION_MISMATCH": 1,
    "HASH_MISMATCH": 1,
    "MULTIPLE_CANDIDATES": 1,
    "NOT_CONFIGURED": 2,
    "IMPORT_FAILED": 3,
    "ERROR": 3,
    "NOT_VERIFIABLE": 4,
}
EXIT_PRECEDENCE = ("ERROR", "IMPORT_FAILED", "NOT_CONFIGURED", "NOT_VERIFIABLE", "PATH_MISMATCH", "VERSION_MISMATCH", "HASH_MISMATCH", "MULTIPLE_CANDIDATES")


class CoreProvenanceError(RuntimeError):
    """Raised by strict verification when imported provenance is unacceptable."""


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "manifest missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"manifest unreadable: {exc}"
    if not isinstance(value, dict):
        return None, "manifest is not an object"
    return value, None


def _version(root: Path) -> str | None:
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _module_root(module: Any) -> Path | None:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None
    return Path(module_file).resolve().parent


def _candidate_paths(sys_path: Iterable[str]) -> list[str]:
    found: list[str] = []
    for raw in sys_path:
        if not raw:
            raw = os.getcwd()
        try:
            candidate = (Path(raw) / "predictor_core").resolve()
        except OSError:
            continue
        if candidate.is_dir() and str(candidate) not in found:
            found.append(str(candidate))
    return found


def expected_identity(vendor_root: Path) -> dict[str, Any]:
    """Read expected vendor identity from bytes plus its manifest metadata."""
    if not vendor_root.is_dir():
        return {"error": "expected vendor directory is missing"}
    manifest, manifest_error = _read_json(vendor_root / MANIFEST_NAME)
    try:
        payload = payload_entries(vendor_root)
        computed_hash = aggregate(payload)
    except OSError as exc:
        return {"error": f"expected vendor read error: {exc}"}
    return {
        "root": str(vendor_root.resolve()),
        "version": _version(vendor_root),
        "computed_hash": computed_hash,
        "manifest_hash": manifest.get("aggregate") if manifest else None,
        "manifest_error": manifest_error,
        "file_count": len(payload),
    }


def inspect_core_provenance(expected_core_root: Path, module: Any | None = None, *, full: bool = False) -> dict[str, Any]:
    """Inspect an imported core without modifying import state.

    Callers that need an actual import should import inside their own isolated
    process first.  Passing ``module`` is useful for a preloaded ``sys.modules``
    scenario and for entrypoint opt-in checks.
    """
    expected = expected_identity(expected_core_root)
    result: dict[str, Any] = {
        "expected_core_root": expected.get("root"),
        "expected_version": expected.get("version"),
        "expected_manifest_hash": expected.get("computed_hash"),
        "expected_declared_manifest_hash": expected.get("manifest_hash"),
        "observed_module_path": None,
        "observed_core_root": None,
        "observed_version": None,
        "observed_manifest_hash": None,
        "path_matches": False,
        "version_matches": False,
        "hash_matches": None,
        "sys_path_sources": _candidate_paths(sys.path),
        "diagnostics": [],
        "status": "ERROR",
        "verification_level": "full" if full else "light",
    }
    if expected.get("error"):
        result.update(status="NOT_VERIFIABLE", diagnostics=[expected["error"]])
        return result
    if expected.get("manifest_error"):
        result["diagnostics"].append(expected["manifest_error"])
    if module is None:
        module = sys.modules.get("predictor_core")
    if module is None:
        result.update(status="IMPORT_FAILED", diagnostics=result["diagnostics"] + ["predictor_core is not imported"])
        return result
    root = _module_root(module)
    module_file = getattr(module, "__file__", None)
    if root is None or module_file is None:
        result.update(status="NOT_VERIFIABLE", diagnostics=result["diagnostics"] + ["imported module has no __file__"])
        return result
    result["observed_module_path"] = str(Path(module_file).resolve())
    result["observed_core_root"] = str(root)
    result["observed_version"] = _version(root)
    result["path_matches"] = root == expected_core_root.resolve()
    result["version_matches"] = result["observed_version"] == expected.get("version")
    if full:
        try:
            result["observed_manifest_hash"] = aggregate(payload_entries(root))
            result["hash_matches"] = result["observed_manifest_hash"] == expected.get("computed_hash")
        except OSError as exc:
            result.update(status="NOT_VERIFIABLE", diagnostics=result["diagnostics"] + [f"observed payload read error: {exc}"])
            return result
    candidates = result["sys_path_sources"]
    if len(candidates) > 1:
        result["diagnostics"].append(f"multiple predictor_core candidates on sys.path: {len(candidates)}")
    if not result["path_matches"]:
        result["status"] = "PATH_MISMATCH"
    elif not result["version_matches"]:
        result["status"] = "VERSION_MISMATCH"
    elif full and not result["hash_matches"]:
        result["status"] = "HASH_MISMATCH"
    else:
        result["status"] = "MATCH"
    return result


def verify_core_provenance(expected_core_root: Path, module: Any | None = None, *, full: bool = True, strict: bool = False) -> dict[str, Any]:
    """Inspect provenance and optionally raise when it does not match expected root."""
    result = inspect_core_provenance(expected_core_root, module, full=full)
    if strict and result["status"] != "MATCH":
        raise CoreProvenanceError(f"predictor_core provenance {result['status']}: {result['diagnostics']}")
    return result


_PROBE = r'''
import importlib
import json
import os
import runpy
import sys

request = json.loads(os.environ["CORE_PROVENANCE_REQUEST"])
consumer_root = request["consumer_root"]
vendor_root = request["vendor_root"]
mode = request["mode"]
if mode == "vendor":
    # Python resolves a package from the directory that *contains* it, not from
    # the package directory itself.
    sys.path.insert(0, os.path.dirname(vendor_root))
elif mode in {"script", "module"}:
    sys.path.insert(0, consumer_root)

run_error = None
exit_code = None
try:
    if mode == "script":
        sys.argv = [request["script"], "--help"]
        runpy.run_path(request["script"], run_name="__main__")
    elif mode == "module":
        sys.argv = [request["module"], "--help"]
        runpy.run_module(request["module"], run_name="__main__")
    else:
        importlib.import_module("predictor_core")
except SystemExit as exc:
    exit_code = int(exc.code) if isinstance(exc.code, int) else 1
except BaseException as exc:
    run_error = f"{type(exc).__name__}: {exc}"

module = sys.modules.get("predictor_core")
print(json.dumps({
    "run_error": run_error,
    "entrypoint_exit_code": exit_code,
    "module_file": getattr(module, "__file__", None),
    "sys_path": sys.path,
}, ensure_ascii=False, sort_keys=True))
'''


def _probe_consumer(consumer_root: Path, vendor_root: Path, *, mode: str, script: str | None, module: str | None, timeout: float) -> dict[str, Any]:
    request = {
        "consumer_root": str(consumer_root.resolve()),
        "vendor_root": str(vendor_root.resolve()),
        "mode": mode,
        "script": script,
        "module": module,
    }
    env = os.environ.copy()
    env["CORE_PROVENANCE_REQUEST"] = json.dumps(request, sort_keys=True)
    # Importing a vendor must not create ``__pycache__`` inside a consumer.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=consumer_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"probe timed out after {timeout:g}s"}
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": "probe did not emit JSON", "stdout": completed.stdout, "stderr": completed.stderr, "returncode": completed.returncode}
    payload.update({"stdout": "\n".join(lines[:-1]), "stderr": completed.stderr, "returncode": completed.returncode})
    return payload


def audit_consumer(consumer: str, consumer_root: Path, *, mode: str = "vendor", script: str | None = None, module: str | None = None, full: bool = True, timeout: float = 10.0) -> dict[str, Any]:
    vendor_root = consumer_root / "vendor" / "predictor_core"
    if not consumer_root.is_dir():
        return {"consumer": consumer, "status": "NOT_CONFIGURED", "diagnostics": ["consumer directory is missing"]}
    if not vendor_root.is_dir():
        return {"consumer": consumer, "status": "NOT_CONFIGURED", "diagnostics": ["vendor/predictor_core is missing"]}
    if mode == "script" and not script:
        return {"consumer": consumer, "status": "NOT_CONFIGURED", "diagnostics": ["--script is required for script mode"]}
    if mode == "module" and not module:
        return {"consumer": consumer, "status": "NOT_CONFIGURED", "diagnostics": ["--module is required for module mode"]}
    probe = _probe_consumer(consumer_root, vendor_root, mode=mode, script=script, module=module, timeout=timeout)
    if probe.get("error"):
        return {"consumer": consumer, "status": "IMPORT_FAILED", "diagnostics": [probe["error"]], "probe": probe}
    if probe.get("run_error"):
        return {"consumer": consumer, "status": "IMPORT_FAILED", "diagnostics": [probe["run_error"]], "probe": probe}
    module_file = probe.get("module_file")
    if not module_file:
        return {"consumer": consumer, "status": "NOT_VERIFIABLE", "diagnostics": ["entrypoint completed without importing predictor_core"], "probe": probe}
    module_root = Path(module_file).resolve().parent
    expected = expected_identity(vendor_root)
    observed_hash = None
    try:
        observed_hash = aggregate(payload_entries(module_root)) if full else None
    except OSError as exc:
        return {"consumer": consumer, "status": "NOT_VERIFIABLE", "diagnostics": [f"cannot read observed core: {exc}"], "probe": probe}
    observed_version = _version(module_root)
    path_matches = expected.get("root") == str(module_root)
    version_matches = expected.get("version") == observed_version
    hash_matches = None if not full else expected.get("computed_hash") == observed_hash
    diagnostics = []
    candidates = _candidate_paths(probe.get("sys_path", []))
    if len(candidates) > 1:
        diagnostics.append(f"multiple predictor_core candidates on sys.path: {len(candidates)}")
    if expected.get("error"):
        diagnostics.append(expected["error"])
        status = "NOT_VERIFIABLE"
    elif not path_matches:
        status = "PATH_MISMATCH"
    elif not version_matches:
        status = "VERSION_MISMATCH"
    elif full and not hash_matches:
        status = "HASH_MISMATCH"
    else:
        status = "MATCH"
    return {
        "consumer": consumer,
        "mode": mode,
        "observed_module_path": str(Path(module_file).resolve()),
        "observed_core_root": str(module_root),
        "expected_core_root": expected.get("root"),
        "observed_version": observed_version,
        "expected_version": expected.get("version"),
        "observed_manifest_hash": observed_hash,
        "expected_manifest_hash": expected.get("computed_hash"),
        "expected_declared_manifest_hash": expected.get("manifest_hash"),
        "path_matches": path_matches,
        "version_matches": version_matches,
        "hash_matches": hash_matches,
        "sys_path_sources": candidates,
        "status": status,
        "diagnostics": diagnostics,
        "probe": {key: probe.get(key) for key in ("entrypoint_exit_code", "returncode", "stdout", "stderr")},
    }


def overall_exit(results: Iterable[dict[str, Any]], *, strict: bool) -> int:
    statuses = {result["status"] for result in results}
    if not strict:
        return 0
    if not statuses:
        return 2
    for status in EXIT_PRECEDENCE:
        if status in statuses:
            return EXIT_CODES[status]
    return 0


def build_report(workspace: Path, consumers: list[str] | None, *, mode: str, script: str | None, module: str | None, full: bool, timeout: float, strict: bool) -> dict[str, Any]:
    if consumers:
        targets = [(name, workspace / name) for name in sorted(set(consumers))]
    else:
        targets = [(name, vendor.parents[1]) for name, vendor in discover_consumers(workspace)]
    results = [audit_consumer(name, root, mode=mode, script=script, module=module, full=full, timeout=timeout) for name, root in targets]
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {
        "workspace_path": str(workspace),
        "mode": mode,
        "verification_level": "full" if full else "light",
        "strict": strict,
        "consumers": results,
        "summary": {"consumer_count": len(results), "statuses": dict(sorted(counts.items()))},
        "exit_code": overall_exit(results, strict=strict),
        "limitations": [
            "default vendor mode verifies an isolated expected-vendor import, not every application entrypoint",
            "script/module modes run with --help and must be selected explicitly to avoid pipelines",
            "the tool reports the current interpreter subprocess; it does not alter parent sys.path or sys.modules",
        ],
    }


def _human(data: dict[str, Any]) -> str:
    lines = [f"predictor_core runtime provenance ({data['verification_level']}, mode={data['mode']})"]
    for result in data["consumers"]:
        lines.append(f"{result['consumer']}: {result['status']} observed={result.get('observed_core_root')} expected={result.get('expected_core_root')}")
        for diagnostic in result.get("diagnostics", []):
            lines.append(f"  diagnostic: {diagnostic}")
    lines.append(f"exit_code: {data['exit_code']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only runtime provenance check for predictor_core")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="check every configured vendor consumer (default)")
    group.add_argument("--consumer", action="append", help="consumer directory name; repeatable")
    parser.add_argument("--strict", action="store_true", help="return non-zero for any non-MATCH result")
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON")
    parser.add_argument("--light", action="store_true", help="skip explicit payload hashing")
    parser.add_argument("--script", help="run a consumer-relative script with --help before inspection")
    parser.add_argument("--module", help="run a consumer-relative module with --help before inspection")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.script and args.module:
        parser.error("--script and --module are mutually exclusive")
    mode = "script" if args.script else "module" if args.module else "vendor"
    workspace = args.workspace.resolve()
    data = build_report(workspace, args.consumer, mode=mode, script=args.script, module=args.module, full=not args.light, timeout=args.timeout, strict=args.strict)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(_human(data))
    return data["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
