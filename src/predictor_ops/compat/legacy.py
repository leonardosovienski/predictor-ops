from __future__ import annotations

import argparse
import warnings
from collections.abc import Sequence
from pathlib import Path

from predictor_ops.models import JobConfig, RuntimeConfig


def translate_legacy_runner(argv: Sequence[str]) -> JobConfig:
    """Translate the generic 1.x runner flags without restoring the tools namespace."""
    warnings.warn(
        "legacy operational_runner flags are deprecated; migrate to a validated jobs file before 3.0",
        DeprecationWarning,
        stacklevel=2,
    )
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("run", nargs="?")
    parser.add_argument("--task", required=True)
    parser.add_argument("--project")
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--max-output-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--heartbeat", type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--provenance-mode", choices=("strict", "permissive"), default="strict")
    parser.add_argument("--consumer-provenance-json")
    known, command = parser.parse_known_args(list(argv))
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("legacy command is required after --")
    explicit = [path for path in (known.heartbeat, known.events, known.lock) if path is not None]
    roots = {path.resolve().parent for path in explicit}
    if len(roots) > 1:
        raise ValueError("legacy heartbeat, events and lock must share one runtime directory")
    runtime_root = next(iter(roots)).parent if roots else RuntimeConfig().root
    provenance = {"legacy_project": known.project} if known.project else {}
    if known.consumer_provenance_json:
        import json

        value = json.loads(known.consumer_provenance_json)
        if not isinstance(value, dict):
            raise ValueError("consumer provenance must be an object")
        provenance.update(value)
    return JobConfig(
        id=known.task,
        command=command,
        cwd=known.cwd,
        timeout_seconds=known.timeout,
        max_output_bytes=known.max_output_bytes,
        provenance_mode=known.provenance_mode,
        provenance=provenance,
        runtime=RuntimeConfig(root=runtime_root),
    )
