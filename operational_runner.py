"""Small, stdlib-only execution envelope for scheduled jobs.

The runner intentionally knows nothing about a domain pipeline.  It records
the process boundary, preserves child output, atomically publishes a
heartbeat, and returns the child result to its caller.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

try:  # Supports both ``python tools/operational_runner.py`` and package imports in tests.
    from tools.secret_redaction import (
        collect_sensitive_values,
        redact_command,
        safe_redact_mapping,
        safe_redact_text,
    )
except ModuleNotFoundError:
    from secret_redaction import (  # type: ignore[no-redef]
        collect_sensitive_values,
        redact_command,
        safe_redact_mapping,
        safe_redact_text,
    )

try:
    from tools.tools_provenance import ToolsProvenanceError, collect_tools_provenance
except ModuleNotFoundError:
    from tools_provenance import ToolsProvenanceError, collect_tools_provenance  # type: ignore[no-redef]

sys.dont_write_bytecode = True

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def redact(value: str) -> str:
    """Compatibility helper for callers that only need a text value."""
    return safe_redact_text(value, collect_sensitive_values(os.environ))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_heartbeat(path: Path, payload: dict[str, Any]) -> None:
    """Publish the current run state atomically; safe for health-check reads."""
    atomic_write_json(path, safe_redact_mapping(payload, collect_sensitive_values(os.environ)))


def append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(safe_redact_mapping(payload, collect_sensitive_values(os.environ)), ensure_ascii=False, sort_keys=True) + "\n")


def _core_summary(project_path: Path) -> dict[str, str]:
    version = project_path / "vendor" / "predictor_core" / "VERSION"
    if version.is_file():
        return {
            "status": "VENDOR_VERSION_DECLARED",
            "version": version.read_text(encoding="utf-8").strip(),
            "scope": "vendor snapshot; child import not observed",
        }
    return {"status": "NOT_APPLICABLE", "scope": "no vendor VERSION found"}


def _consumer_provenance(raw: str | None, sensitive_values: Sequence[str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"consumer provenance must be a JSON object: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("consumer provenance must be a JSON object")
    return safe_redact_mapping(value, sensitive_values)


def _base_record(args: argparse.Namespace, run_id: str, started_at: str, sensitive_values: Sequence[str]) -> dict[str, Any]:
    project_path = Path(args.cwd).resolve()
    command = redact_command(args.command, sensitive_values)
    record = {
        "run_id": run_id,
        "task_name": args.task,
        "project": args.project,
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "duration_seconds": None,
        "status": "STARTED",
        "exit_code": None,
        "command": command,
        "script_path": command[0] if command else None,
        "working_directory": str(project_path),
        "python_executable": command[0] if command else sys.executable,
        "core_provenance": _core_summary(project_path),
        "expected_artifact": str(Path(args.expected_artifact).resolve()) if args.expected_artifact else None,
        "error_summary": None,
        "log_path": str(Path(args.log).resolve()),
        "heartbeat_path": str(Path(args.heartbeat).resolve()),
    }
    record["tools_provenance"] = collect_tools_provenance(strict=args.provenance_mode == "strict")
    consumer = _consumer_provenance(args.consumer_provenance_json, sensitive_values)
    if consumer is not None:
        record["consumer_provenance"] = consumer
    return record


def _finish(record: dict[str, Any], status: str, exit_code: int, started: float, error: str | None = None, sensitive_values: Sequence[str] = ()) -> dict[str, Any]:
    record = dict(record)
    record.update(
        finished_at_utc=utc_now(),
        duration_seconds=round(time.monotonic() - started, 3),
        status=status,
        exit_code=exit_code,
        error_summary=safe_redact_text(error, sensitive_values)[:1000] if error else None,
    )
    return record


def run(args: argparse.Namespace) -> int:
    if not args.command:
        raise ValueError("a child command is required after --")
    cwd = Path(args.cwd)
    started_monotonic = time.monotonic()
    sensitive_values = collect_sensitive_values(os.environ)
    record = _base_record(args, uuid.uuid4().hex, utc_now(), sensitive_values)
    heartbeat = Path(args.heartbeat)
    event_log = Path(args.event_log)
    log_path = Path(args.log)
    lock_path = Path(args.lock) if args.lock else heartbeat.with_suffix(heartbeat.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if not cwd.is_dir():
        finished = _finish(record, "FAILED", 3, started_monotonic, f"working directory does not exist: {cwd}", sensitive_values)
        write_heartbeat(heartbeat, finished)
        append_event(event_log, finished)
        return 3

    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        finished = _finish(record, "SKIPPED", 4, started_monotonic, f"another instance holds lock: {lock_path}", sensitive_values)
        write_heartbeat(heartbeat, finished)
        append_event(event_log, finished)
        return 4

    try:
        os.write(lock_fd, record["run_id"].encode("ascii"))
        os.close(lock_fd)
        write_heartbeat(heartbeat, record)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        with log_path.open("a", encoding="utf-8", errors="replace") as output:
            output.write(f"{record['started_at_utc']} STARTED {record['task_name']} run_id={record['run_id']}\n")
            output.flush()
            try:
                child = subprocess.Popen(args.command, cwd=str(cwd), env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                try:
                    captured, _ = child.communicate(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate()
                    raise
                output.write(safe_redact_text(captured, sensitive_values))
                child_exit = child.returncode
                if child_exit == 0 and args.expected_artifact and not Path(args.expected_artifact).exists():
                    finished = _finish(record, "PARTIAL", 1, started_monotonic, "expected artifact was not found", sensitive_values)
                elif args.partial_exit_code is not None and child_exit == args.partial_exit_code:
                    finished = _finish(record, "PARTIAL", child_exit, started_monotonic, "child reported a partial execution", sensitive_values)
                elif child_exit == 0:
                    finished = _finish(record, "SUCCEEDED", 0, started_monotonic, sensitive_values=sensitive_values)
                else:
                    finished = _finish(record, "FAILED", child_exit or 1, started_monotonic, f"child exited with {child_exit}", sensitive_values)
            except subprocess.TimeoutExpired:
                finished = _finish(record, "TIMED_OUT", 124, started_monotonic, f"timeout after {args.timeout} seconds", sensitive_values)
            except OSError as exc:
                finished = _finish(record, "FAILED", 3, started_monotonic, str(exc), sensitive_values)
            output.write(f"{finished['finished_at_utc']} {finished['status']} exit={finished['exit_code']}\n")
        write_heartbeat(heartbeat, finished)
        append_event(event_log, finished)
        return int(finished["exit_code"])
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a scheduled child command with an observable envelope.")
    parser.add_argument("--task", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--heartbeat", required=True)
    parser.add_argument("--event-log", required=True)
    parser.add_argument("--expected-artifact")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--lock")
    parser.add_argument("--partial-exit-code", type=int)
    parser.add_argument("--provenance-mode", choices=("strict", "permissive"), default="strict")
    parser.add_argument("--consumer-provenance-json", help="optional redacted JSON object supplied by the consumer")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values[:1] == ["run"]:
        values = values[1:]
    if values in (["--help"], ["-h"]):
        build_parser().print_help()
        return 0
    if "--" not in values:
        print("operational_runner configuration error: child command must follow --", file=sys.stderr)
        return 3
    boundary = values.index("--")
    args = build_parser().parse_args(values[:boundary])
    args.command = values[boundary + 1:]
    try:
        return run(args)
    except (ValueError, OSError, ToolsProvenanceError) as exc:
        print(f"operational_runner configuration error: {redact(str(exc))}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
