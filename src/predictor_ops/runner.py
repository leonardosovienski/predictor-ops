from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from . import __version__
from .models import JobConfig, RunStatus
from .observability import logger
from .operations import economic_lock_id, kill_switch_reasons
from .provenance import ProvenanceError, collect_provenance
from .redaction import redact, redact_command, redact_text, sensitive_values
from .runtime import RuntimeBackend, append_jsonl, atomic_json, backend


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_status: RunStatus
    exit_code: int
    record: dict[str, Any]


def _terminate_tree(process: subprocess.Popen[bytes], grace: float = 5) -> dict[str, Any]:
    if process.poll() is not None:
        return {"requested": False, "method": "already_exited"}
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        return {"requested": True, "method": "taskkill_tree", "return_code": result.returncode}
    try:
        process_group = os.getpgid(process.pid)
        os.killpg(process_group, signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            process.wait(grace)
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return {"requested": True, "method": "process_group_sigterm"}
        os.killpg(process_group, signal.SIGKILL)
        process.wait(grace)
        return {"requested": True, "method": "process_group_sigkill"}
    except ProcessLookupError:
        return {"requested": True, "method": "already_exited"}


def _drain(
    stream: Any,
    sink: bytearray,
    secrets: tuple[str, ...],
    limit: int,
    truncated: threading.Event,
    errors: list[Exception],
) -> None:
    try:
        while chunk := stream.readline():
            data = redact_text(chunk.decode("utf-8", errors="replace"), secrets).encode("utf-8")
            remaining = max(0, limit - len(sink))
            sink.extend(data[:remaining])
            if len(data) > remaining:
                truncated.set()
    except Exception as exc:
        errors.append(exc)


def _close_process_resources(
    process: subprocess.Popen[bytes] | None,
    reader: threading.Thread | None,
    reader_errors: list[Exception],
) -> dict[str, Any] | None:
    """Deterministically reap a child, drain output, and close every owned stream."""
    if process is None:
        return None
    forced: dict[str, Any] | None = None
    if process.poll() is None:
        forced = _terminate_tree(process)
        forced["reason"] = "exception_cleanup"
    with suppress(subprocess.TimeoutExpired):
        process.wait(5)
    if reader is not None:
        reader.join(5)
        if reader.is_alive():
            # A descendant may have inherited stdout after the direct child
            # exited. The process tree is already gone, so closing now cannot
            # discard output that can still be produced by the owned tree.
            if process.stdout is not None and not process.stdout.closed:
                process.stdout.close()
            reader.join(5)
        if reader.is_alive():
            reader_errors.append(RuntimeError("output reader did not terminate"))
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()
    return forced


def run_job(
    job: JobConfig, *, runtime_backend: RuntimeBackend | None = None, shutdown: threading.Event | None = None
) -> RunResult:
    started_mono, started_at, run_id = time.monotonic(), utc_now(), uuid.uuid4().hex
    environment = os.environ.copy()
    environment.update(job.environment)
    secrets = sensitive_values(environment)
    runtime_backend = runtime_backend or backend(job.runtime)
    lock_id = economic_lock_id(job)
    lock = runtime_backend.acquire(lock_id, run_id, job.runtime.lock_stale_after_seconds)
    job_root = job.runtime.root / job.id
    heartbeat, events = job_root / "heartbeat.json", job_root / "events.jsonl"
    idempotency_record = job.runtime.root / "idempotency" / f"{lock_id}.json"
    base: dict[str, Any] = {
        "schema_version": "1",
        "service": "predictor_ops",
        "library_version": __version__,
        "job_id": job.id,
        "job_type": job.job_type,
        "economic_key": job.economic_key.model_dump(mode="json") if job.economic_key else None,
        "economic_lock_id": lock_id,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "run_status": RunStatus.WAITING,
        "scientific_state": job.scientific_state,
        "command": redact_command(job.command, secrets),
        "cwd": str(job.cwd.resolve()) if job.cwd else None,
        "provenance": redact(job.provenance, secrets),
    }
    if not lock.acquired:
        record = {
            **base,
            "run_status": RunStatus.SKIPPED,
            "finished_at": utc_now(),
            "reason": "lock_not_acquired",
        }
        atomic_json(job_root / f"skipped.{run_id}.json", record)
        append_jsonl(events, record)
        return RunResult(run_id, RunStatus.SKIPPED, 0, record)

    if idempotency_record.exists():
        try:
            previous_attempt = json.loads(idempotency_record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous_attempt = {"state": "UNKNOWN"}
        if previous_attempt.get("state") == "SUCCEEDED" or job.capital_permission:
            record = {
                **base,
                "run_status": RunStatus.SKIPPED,
                "finished_at": utc_now(),
                "reason": "economic_operation_already_claimed",
                "previous_attempt": previous_attempt,
            }
            atomic_json(job_root / f"skipped.{run_id}.json", record)
            append_jsonl(events, record)
            lock.release()
            return RunResult(run_id, RunStatus.SKIPPED, 0, record)

    kill_reasons = kill_switch_reasons(job)
    if kill_reasons:
        record = {
            **base,
            "run_status": RunStatus.SKIPPED,
            "finished_at": utc_now(),
            "reason": "kill_switch_open",
            "kill_switch_reasons": kill_reasons,
        }
        atomic_json(job_root / f"skipped.{run_id}.json", record)
        append_jsonl(events, record)
        lock.release()
        return RunResult(run_id, RunStatus.SKIPPED, 0, record)

    if job.economic_key is not None:
        atomic_json(
            idempotency_record,
            {"state": "IN_PROGRESS", "job_id": job.id, "run_id": run_id, "claimed_at": utc_now()},
        )

    stop = shutdown or threading.Event()
    output, truncated = bytearray(), threading.Event()
    process: subprocess.Popen[bytes] | None = None
    reader: threading.Thread | None = None
    reader_errors: list[Exception] = []
    termination: dict[str, Any] | None = None
    status, exit_code = RunStatus.FAILED, 1
    record = {**base, "run_status": RunStatus.WAITING}
    try:
        record["library_provenance"] = collect_provenance(strict=job.provenance_mode == "strict")
        popen_args: dict[str, Any] = {
            "cwd": job.cwd,
            "env": environment,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            popen_args["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(
                subprocess, "CREATE_NO_WINDOW", 0
            )
        else:
            popen_args["start_new_session"] = True
        spawned = cast("subprocess.Popen[bytes]", subprocess.Popen(job.command, **popen_args))
        process = spawned
        record.update(run_status=RunStatus.WAITING, pid=spawned.pid)
        atomic_json(heartbeat, record)
        reader = threading.Thread(
            target=_drain,
            args=(spawned.stdout, output, secrets, job.max_output_bytes, truncated, reader_errors),
            name=f"predictor-ops-output-{run_id}",
        )
        reader.start()
        # The command timeout measures child execution, not provenance and
        # process-setup work performed before the child exists.
        deadline, next_heartbeat = time.monotonic() + job.timeout_seconds, time.monotonic()
        while spawned.poll() is None:
            now = time.monotonic()
            if stop.is_set() or now >= deadline:
                termination = _terminate_tree(spawned)
                status, exit_code = RunStatus.FAILED, 124 if now >= deadline else 130
                termination["reason"] = "timeout" if now >= deadline else "shutdown"
                break
            if now >= next_heartbeat:
                if not lock.refresh():
                    termination = _terminate_tree(spawned)
                    termination["reason"] = "lock_lost"
                    status, exit_code = RunStatus.FAILED, 75
                    break
                record["heartbeat_at"] = utc_now()
                atomic_json(heartbeat, record)
                next_heartbeat = now + job.heartbeat_interval_seconds
            time.sleep(min(0.1, job.heartbeat_interval_seconds))
        spawned.wait()
        if termination is None:
            exit_code = int(spawned.returncode or 0)
            status = job.exit_statuses.get(exit_code, RunStatus.FAILED)
        if status is RunStatus.SUCCEEDED and job.expected_artifact and not job.expected_artifact.exists():
            status, exit_code = RunStatus.PARTIAL, 4
    except (OSError, ValueError, ProvenanceError) as exc:
        record["error"] = redact_text(exc, secrets)
        status, exit_code = RunStatus.CONFIGURATION_ERROR, 3
    finally:
        forced_cleanup = _close_process_resources(process, reader, reader_errors)
        if forced_cleanup is not None and termination is None:
            termination = forced_cleanup
        if reader_errors:
            status, exit_code = RunStatus.FAILED, 74
            record["error"] = redact_text(reader_errors[0], secrets)
        record.update(
            run_status=status,
            exit_code=exit_code,
            finished_at=utc_now(),
            duration_ms=round((time.monotonic() - started_mono) * 1000),
            output={
                "text": output.decode("utf-8", errors="replace"),
                "bytes": len(output),
                "truncated": truncated.is_set(),
            },
        )
        if termination:
            record["termination"] = termination
        record = redact(record, secrets)
        persistence_errors: list[Exception] = []
        if job.economic_key is not None:
            try:
                atomic_json(
                    idempotency_record,
                    {
                        "state": status,
                        "job_id": job.id,
                        "run_id": run_id,
                        "updated_at": utc_now(),
                        "requires_reconciliation": bool(
                            job.capital_permission and status is not RunStatus.SUCCEEDED
                        ),
                    },
                )
            except Exception as exc:
                persistence_errors.append(exc)
        try:
            atomic_json(heartbeat, record)
        except Exception as exc:
            persistence_errors.append(exc)
        try:
            append_jsonl(events, record)
        except Exception as exc:
            persistence_errors.append(exc)
        lock.release()
        logger().info(
            "job_finished",
            extra={
                "fields": {
                    "job_id": job.id,
                    "run_id": run_id,
                    "run_status": status,
                    "duration_ms": record["duration_ms"],
                }
            },
        )
        if persistence_errors:
            raise OSError("terminal artifact persistence failed") from persistence_errors[0]
    return RunResult(run_id, status, exit_code, record)
