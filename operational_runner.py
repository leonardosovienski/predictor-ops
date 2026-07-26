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
import signal
import subprocess
import sys
import threading
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


def _replace_with_retry(temporary: Path, path: Path, attempts: int = 6, initial_delay: float = 0.01) -> None:
    """os.replace, retrying on transient Windows sharing-violation errors.

    Auditoria hostil 2026-07-17 (rodada "tools/"): dois processos perdendo a
    corrida do lock escreviam heartbeat concorrentemente (OP-1; o perdedor
    hoje escreve em skipped_heartbeat_path, mas dois perdedores simultâneos
    ainda podem colidir no sidecar) — no Windows, os.replace pode lançar
    PermissionError (WinError 5) quando o destino está momentaneamente aberto
    por OUTRO os.replace concorrente (MoveFileEx com MOVEFILE_REPLACE_EXISTING
    falha nesse caso; diferente do POSIX rename(2), que não tem essa janela).
    A colisão é transitória — um retry curto resolve sem mudar a semântica de
    "quem escreveu por último vence".
    """
    delay = initial_delay
    for attempt in range(attempts):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temporary, path)
    except BaseException:
        # Never leave an orphaned temp file behind on failure (disk full,
        # process killed mid-write, etc.) — matches the cleanup pattern in
        # tools/release_manifest.py. The real heartbeat/JSONL file at `path`
        # is untouched until os.replace succeeds.
        if temporary.exists():
            temporary.unlink()
        raise


def write_heartbeat(path: Path, payload: dict[str, Any]) -> None:
    """Publish the current run state atomically; safe for health-check reads."""
    atomic_write_json(path, safe_redact_mapping(payload, collect_sensitive_values(os.environ)))


def skipped_heartbeat_path(heartbeat: Path) -> Path:
    """Sidecar heartbeat written by a run that lost the lock race.

    O heartbeat principal pertence exclusivamente ao dono do lock: um perdedor
    que escrevesse nele podia sobrescrever o estado RUNNING/final do vencedor
    ("último a escrever vence") e era a origem da colisão de os.replace no
    Windows absorvida por _replace_with_retry. O registro SKIPPED continua
    observável aqui e no event log (serializado por lock próprio)."""
    return heartbeat.with_name(f"{heartbeat.stem}.skipped{heartbeat.suffix or '.json'}")


def append_event(path: Path, payload: dict[str, Any]) -> None:
    """Append one durable JSONL record serialized across runner processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(safe_redact_mapping(payload, collect_sensitive_values(os.environ)), ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    lock_path = path.with_name(f".{path.name}.append.lock")
    deadline = time.monotonic() + 30
    lock_descriptor: int | None = None
    while lock_descriptor is None:
        try:
            lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except (FileExistsError, PermissionError):
            try:
                stale = time.time() - lock_path.stat().st_mtime >= 300
            except FileNotFoundError:
                continue
            if stale:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise OSError(f"timed out waiting for JSONL append lock: {lock_path}")
            time.sleep(0.01)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        os.close(lock_descriptor)
        descriptor = os.open(path, flags, 0o600)
        # A single append write prevents records from being interleaved by
        # independent runners sharing this JSONL file.  Partial writes are
        # treated as an operational failure rather than emitting invalid JSONL.
        try:
            if os.write(descriptor, encoded) != len(encoded):
                raise OSError("incomplete JSONL event write")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


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


def _configuration_failure_record(args: argparse.Namespace, run_id: str, started_at: str, started: float, error: Exception, sensitive_values: Sequence[str]) -> dict[str, Any]:
    """Create an observable fail-closed result when setup cannot be validated."""
    command = redact_command(args.command, sensitive_values)
    record: dict[str, Any] = {
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
        "working_directory": str(Path(args.cwd).resolve()),
        "python_executable": command[0] if command else sys.executable,
        "core_provenance": _core_summary(Path(args.cwd).resolve()),
        "expected_artifact": str(Path(args.expected_artifact).resolve()) if args.expected_artifact else None,
        "log_path": str(Path(args.log).resolve()),
        "heartbeat_path": str(Path(args.heartbeat).resolve()),
        "tools_provenance": {"status": "UNAVAILABLE", "error": safe_redact_text(error, sensitive_values)[:1000]},
    }
    return _finish(record, "FAILED", 3, started, str(error), sensitive_values)


def _lock_is_stale(path: Path, maximum_age: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime >= maximum_age
    except FileNotFoundError:
        return False


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check for a lock-owning PID.

    A read failure (permission denied, transient race) is treated as
    "can't tell" and returns True — fail toward NOT reclaiming, never toward
    silently stealing a live process's lock. Mirrors the Windows
    OpenProcess/POSIX os.kill(pid, 0) pattern already used elsewhere in the
    ecosystem (previsao-cripto's own lock)."""
    if pid <= 0:
        return True
    if sys.platform == "win32":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def _lock_owner_pid_dead(path: Path) -> bool:
    """True only when the lock content is readable, names a PID, and that PID
    is confirmed dead. Anything else (unreadable, no pid field, alive) is
    False — i.e. "not confirmed dead", which keeps the existing age-only
    policy as the fallback rather than ever reclaiming more eagerly than
    before on ambiguous input."""
    try:
        content = json.loads(path.read_text(encoding="ascii"))
        pid = content.get("pid")
    except (OSError, ValueError, AttributeError):
        return False
    if not isinstance(pid, int):
        return False
    return not _pid_alive(pid)


def _acquire_run_lock(path: Path, run_id: str, stale_after: float) -> dict[str, Any]:
    """Acquire a lock, reclaiming locks older than the declared policy OR
    whose recorded owner PID is confirmed dead (auditoria hostil 2026-07-17:
    a lock orphaned by a hard kill — power loss, OOM-killer, a scheduler that
    force-terminates past its own timeout — used to sit unreclaimed for the
    entire `stale_after` window, up to 24h by default, even though the owning
    process plainly no longer existed; on a daily schedule that could skip
    two runs in a row for a single hard-kill event). PID liveness is an
    ADDITIONAL fast path, never a replacement for the age check: if the lock
    content can't be read or has no pid, the original age-only policy still
    applies unchanged."""
    reclaimed_age: float | None = None
    reclaimed_reason: str | None = None
    for _ in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                age = max(0.0, time.time() - path.stat().st_mtime)
            except FileNotFoundError:
                continue
            owner_dead = _lock_owner_pid_dead(path)
            if age < stale_after and not owner_dead:
                return {"acquired": False, "path": str(path.resolve()), "reclaimed": False, "age_seconds": round(age, 3)}
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            reclaimed_age = age
            reclaimed_reason = "owner_pid_dead" if owner_dead else "age_exceeded"
            continue
        try:
            os.write(descriptor, json.dumps({"run_id": run_id, "pid": os.getpid(), "created_at_utc": utc_now()}, sort_keys=True).encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {"acquired": True, "path": str(path.resolve()), "reclaimed": reclaimed_age is not None,
                "reclaimed_age_seconds": round(reclaimed_age, 3) if reclaimed_age is not None else None,
                "reclaimed_reason": reclaimed_reason}
    return {"acquired": False, "path": str(path.resolve()), "reclaimed": False, "age_seconds": None}


def _terminate_process_tree(child: subprocess.Popen[bytes]) -> dict[str, Any]:
    """Terminate the child and descendants created by this runner."""
    result: dict[str, Any] = {"attempted": True, "method": "taskkill" if os.name == "nt" else "process_group", "completed": False, "error": None}
    if child.poll() is not None:
        result["completed"] = True
        return result
    try:
        if os.name == "nt":
            completed = subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0)
            result["taskkill_exit_code"] = completed.returncode
        else:
            os.killpg(child.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = safe_redact_text(exc)
    if child.poll() is None:
        child.kill()
        result["fallback"] = "child_kill"
    result["completed"] = child.poll() is not None
    return result


def _drain_redacted_output(child: subprocess.Popen[bytes], output: Any, sensitive_values: Sequence[str], max_output_bytes: int) -> dict[str, Any]:
    """Drain output without keeping an unbounded raw child stream in memory."""
    state: dict[str, Any] = {"written": 0, "truncated": False, "error": None}
    # Keep enough raw suffix to avoid persisting a secret split across chunks.
    suffix = max(8192, max((len(item) for item in sensitive_values), default=0) + 1024)

    def write_redacted(raw: bytes) -> None:
        if not raw:
            return
        remaining = max_output_bytes - state["written"]
        if remaining <= 0:
            state["truncated"] = True
            return
        # Only bytes that could be persisted (plus the secret-boundary
        # suffix) need redaction.  The rest is drained and discarded.
        text = safe_redact_text(raw[:remaining + suffix], sensitive_values)
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) > remaining:
            encoded = encoded[:remaining]
            state["truncated"] = True
        output.write(encoded.decode("utf-8", errors="replace"))
        state["written"] += len(encoded)

    def drain() -> None:
        pending = b""
        try:
            assert child.stdout is not None
            while True:
                # Use the raw pipe rather than BufferedReader.read(): on
                # Windows the latter may wait for its requested buffer size
                # and deadlock a verbose child before it can close the pipe.
                chunk = child.stdout.raw.read(65536)
                if not chunk:
                    break
                pending += chunk
                if len(pending) > suffix:
                    write_redacted(pending[:-suffix])
                    pending = pending[-suffix:]
            write_redacted(pending)
        except (OSError, ValueError) as exc:
            state["error"] = exc

    thread = threading.Thread(target=drain, name="operational-runner-output", daemon=True)
    thread.start()
    state["thread"] = thread
    return state


def run(args: argparse.Namespace) -> int:
    if not args.command:
        raise ValueError("a child command is required after --")
    cwd = Path(args.cwd)
    started_monotonic = time.monotonic()
    sensitive_values = collect_sensitive_values(os.environ)
    run_id, started_at = uuid.uuid4().hex, utc_now()
    try:
        record = _base_record(args, run_id, started_at, sensitive_values)
    except (ValueError, OSError, ToolsProvenanceError) as exc:
        finished = _configuration_failure_record(args, run_id, started_at, started_monotonic, exc, sensitive_values)
        write_heartbeat(Path(args.heartbeat), finished)
        append_event(Path(args.event_log), finished)
        return 3
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

    lock = _acquire_run_lock(lock_path, record["run_id"], args.lock_stale_after)
    record["lock"] = lock
    if not lock["acquired"]:
        finished = _finish(record, "SKIPPED", 4, started_monotonic, f"another instance holds lock: {lock_path}", sensitive_values)
        write_heartbeat(skipped_heartbeat_path(heartbeat), finished)
        append_event(event_log, finished)
        return 4

    try:
        write_heartbeat(heartbeat, record)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        with log_path.open("a", encoding="utf-8", errors="replace") as output:
            output.write(f"{record['started_at_utc']} STARTED {record['task_name']} run_id={record['run_id']}\n")
            output.flush()
            try:
                popen_options: dict[str, Any] = {"cwd": str(cwd), "env": environment, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
                if os.name == "nt":
                    # CREATE_NO_WINDOW junto do grupo de processos: a tarefa
                    # agendada roda sob pythonw.exe, que nao tem console, entao
                    # este filho — um python.exe de console — ganharia um
                    # console PROPRIO E VISIVEL a cada disparo. O stdout ja e
                    # PIPE e drenado, entao nada de saida se perde.
                    popen_options["creationflags"] = (
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                        | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
                else:
                    popen_options["start_new_session"] = True
                child = subprocess.Popen(args.command, **popen_options)
                drain = _drain_redacted_output(child, output, sensitive_values, args.max_output_bytes)
                try:
                    child.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    record["termination"] = _terminate_process_tree(child)
                    child.wait()
                    drain["thread"].join()
                    record["output"] = {"truncated": drain["truncated"], "bytes_persisted": drain["written"], "limit_bytes": args.max_output_bytes}
                    if drain["truncated"]:
                        output.write("\n[OUTPUT_TRUNCATED]\n")
                    raise
                drain["thread"].join()
                record["output"] = {"truncated": drain["truncated"], "bytes_persisted": drain["written"], "limit_bytes": args.max_output_bytes}
                if drain["error"] is not None:
                    raise drain["error"]
                if drain["truncated"]:
                    output.write("\n[OUTPUT_TRUNCATED]\n")
                child_exit = child.returncode
                consumer_status = None
                if args.consumer_status_json:
                    try:
                        candidate = json.loads(Path(args.consumer_status_json).read_text(encoding="utf-8"))
                        if isinstance(candidate, dict) and isinstance(candidate.get("status"), str):
                            consumer_status = {key: candidate[key] for key in ("status", "reason", "collection_run_id", "accepted", "ambiguous", "invalid", "complete", "input_present") if key in candidate}
                    except (OSError, json.JSONDecodeError):
                        consumer_status = {"status": "SOURCE_UNAVAILABLE", "reason": "CONSUMER_STATUS_UNAVAILABLE"}
                if child_exit == 0 and consumer_status and consumer_status["status"] in {"SOURCE_UNAVAILABLE", "NO_UPSTREAM_EVENTS"}:
                    finished = _finish(record, consumer_status["status"], 0, started_monotonic, sensitive_values=sensitive_values)
                    finished["operational_status"] = consumer_status
                elif child_exit == 0 and args.expected_artifact and not Path(args.expected_artifact).exists():
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
    parser.add_argument("--lock-stale-after", type=float, default=86400.0, help="seconds before an orphaned run lock may be reclaimed (default: 86400)")
    parser.add_argument("--max-output-bytes", type=int, default=10 * 1024 * 1024, help="maximum redacted child output persisted per run")
    parser.add_argument("--partial-exit-code", type=int)
    parser.add_argument("--provenance-mode", choices=("strict", "permissive"), default="strict")
    parser.add_argument("--consumer-provenance-json", help="optional redacted JSON object supplied by the consumer")
    parser.add_argument("--consumer-status-json", help="optional structured operational status JSON supplied by the consumer")
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
    if args.timeout is not None and args.timeout <= 0:
        print("operational_runner configuration error: --timeout must be positive", file=sys.stderr)
        return 3
    if args.lock_stale_after <= 0 or args.max_output_bytes <= 0:
        print("operational_runner configuration error: lock and output limits must be positive", file=sys.stderr)
        return 3
    try:
        return run(args)
    except (ValueError, OSError, ToolsProvenanceError) as exc:
        print(f"operational_runner configuration error: {redact(str(exc))}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
