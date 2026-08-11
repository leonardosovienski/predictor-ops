from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import __version__
from .config import FileJobConfigSource, load_job
from .models import JobConfig
from .provenance import collect_provenance, safe_serialize
from .redaction import redact_text
from .runner import run_job


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="predictor-ops")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run", help="run one validated job")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path)
    source.add_argument("--command", nargs=argparse.REMAINDER)
    run.add_argument("--job")
    run.add_argument("--job-id", default="adhoc")
    run.add_argument("--runtime-root", type=Path)
    validate = commands.add_parser("validate", help="validate a jobs file")
    validate.add_argument("config", type=Path)
    provenance = commands.add_parser("provenance", help="verify the installed wheel or a clean source checkout")
    provenance.add_argument("--source-root", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "validate":
            jobs = FileJobConfigSource(args.config).load()
            print(json.dumps({"valid": True, "jobs": len(jobs.jobs)}, sort_keys=True))
            return 0
        if args.action == "provenance":
            print(safe_serialize(collect_provenance(strict=True, source_root=args.source_root)))
            return 0
        if args.config:
            if not args.job:
                raise ValueError("--job is required with --config")
            job = load_job(args.config, args.job)
        else:
            command = args.command
            if command and command[0] == "--":
                command = command[1:]
            job = JobConfig(id=args.job_id, command=command)
        if args.runtime_root:
            job.runtime.root = args.runtime_root
        shutdown = threading.Event()
        previous: dict[int, Any] = {}
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda _s, _f: shutdown.set())
        try:
            return run_job(job, shutdown=shutdown).exit_code
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    except (OSError, KeyError, ValueError, ValidationError, RuntimeError) as exc:
        print(json.dumps({"status": "CONFIGURATION_ERROR", "error": redact_text(exc)}, sort_keys=True), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
