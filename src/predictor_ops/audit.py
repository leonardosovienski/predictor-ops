from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any

from .runtime import append_jsonl


class CycleStage(StrEnum):
    SNAPSHOT = "snapshot"
    FORECAST = "forecast"
    DECISION = "decision"
    ORDER = "order"
    FILL = "fill"
    SETTLEMENT = "settlement"


GENESIS_HASH = "0" * 64
_NEXT_STAGES = {
    None: {CycleStage.SNAPSHOT},
    CycleStage.SNAPSHOT: {CycleStage.FORECAST},
    CycleStage.FORECAST: {CycleStage.DECISION},
    CycleStage.DECISION: {CycleStage.ORDER},
    CycleStage.ORDER: {CycleStage.FILL},
    CycleStage.FILL: {CycleStage.FILL, CycleStage.SETTLEMENT},
    CycleStage.SETTLEMENT: set(),
}


def _digest(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class AppendOnlyAuditLog:
    """Fsynced hash chain. Corruption is detected before any new event is appended."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(f".{self.path.name}.chain.lock")
        deadline = time.monotonic() + 30
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"audit chain lock timeout: {self.path.name}") from None
                time.sleep(0.01)
        try:
            os.close(descriptor)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def verify(self) -> str:
        previous = GENESIS_HASH
        cycle_stages: dict[str, CycleStage] = {}
        if not self.path.exists():
            return previous
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                record = json.loads(line)
                claimed = record.pop("hash")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid audit record at line {number}") from exc
            if record.get("previous_hash") != previous or _digest(record) != claimed:
                raise ValueError(f"broken audit chain at line {number}")
            try:
                stage = CycleStage(record["stage"])
                cycle_id = str(record["cycle_id"])
            except (ValueError, KeyError) as exc:
                raise ValueError(f"invalid cycle stage at line {number}") from exc
            prior_stage = cycle_stages.get(cycle_id)
            if stage not in _NEXT_STAGES[prior_stage]:
                raise ValueError(f"invalid cycle transition at line {number}: {prior_stage} -> {stage}")
            cycle_stages[cycle_id] = stage
            previous = claimed
        return previous

    def _last_cycle_stage(self, cycle_id: str) -> CycleStage | None:
        if not self.path.exists():
            return None
        last: CycleStage | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("cycle_id") == cycle_id:
                last = CycleStage(record["stage"])
        return last

    def append(self, stage: CycleStage, payload: dict[str, Any], *, event_id: str, cycle_id: str) -> dict[str, Any]:
        with self._transaction():
            previous = self.verify()
            prior_stage = self._last_cycle_stage(cycle_id)
            if stage not in _NEXT_STAGES[prior_stage]:
                raise ValueError(f"invalid cycle transition: {prior_stage} -> {stage}")
            record = {
                "schema_version": "1",
                "event_id": event_id,
                "cycle_id": cycle_id,
                "stage": stage,
                "payload": payload,
                "previous_hash": previous,
            }
            record["hash"] = _digest(record)
            append_jsonl(self.path, record)
        return record
