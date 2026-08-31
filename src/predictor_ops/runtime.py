from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import RuntimeConfig


class Lock(Protocol):
    @property
    def acquired(self) -> bool: ...
    def refresh(self) -> bool: ...
    def release(self) -> None: ...


class RuntimeBackend(Protocol):
    def acquire(self, job_id: str, run_id: str, ttl: float) -> Lock: ...


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        deadline = time.monotonic() + 1
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows scanners and indexers can briefly hold a newly fsynced
                # file. Preserve atomic replacement while tolerating that race.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
    finally:
        temporary.unlink(missing_ok=True)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
    lock = path.with_name(f".{path.name}.append.lock")
    deadline = time.monotonic() + 30
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except (FileExistsError, PermissionError):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"event log lock timeout: {path.name}") from None
            try:
                stale = time.time() - lock.stat().st_mtime > 300
            except FileNotFoundError:
                continue
            if stale:
                lock.unlink(missing_ok=True)
            else:
                time.sleep(0.01)
    try:
        os.close(descriptor)
        fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            if os.write(fd, encoded) != len(encoded):
                raise OSError("partial JSONL write")
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        lock.unlink(missing_ok=True)


@dataclass
class LocalLock:
    path: Path
    run_id: str
    _acquired: bool

    @property
    def acquired(self) -> bool:
        return self._acquired

    def _owned(self) -> bool:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))["run_id"] == self.run_id
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def refresh(self) -> bool:
        if not self._owned():
            return False
        os.utime(self.path, None)
        return True

    def release(self) -> None:
        if self._owned():
            self.path.unlink(missing_ok=True)


class LocalBackend:
    def __init__(self, root: Path) -> None:
        self.root = root

    def acquire(self, job_id: str, run_id: str, ttl: float) -> LocalLock:
        path = self.root / job_id / "run.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    stale = time.time() - path.stat().st_mtime >= ttl
                    owner = json.loads(path.read_text(encoding="utf-8"))
                    pid = int(owner.get("pid", -1))
                    if pid > 0:
                        if sys.platform == "win32":
                            import ctypes

                            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                            dead = not bool(handle)
                            if handle:
                                ctypes.windll.kernel32.CloseHandle(handle)
                        else:
                            try:
                                os.kill(pid, 0)
                                dead = False
                            except ProcessLookupError:
                                dead = True
                            except OSError:
                                dead = False
                    else:
                        dead = False
                except (OSError, ValueError, TypeError):
                    stale, dead = False, False
                if stale or dead:
                    quarantine = path.with_name(f"run.lock.stale.{uuid.uuid4().hex}")
                    try:
                        os.replace(path, quarantine)
                        quarantine.unlink(missing_ok=True)
                    except FileNotFoundError:
                        pass
                    continue
                return LocalLock(path, run_id, False)
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump({"run_id": run_id, "pid": os.getpid(), "created_at": time.time()}, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                return LocalLock(path, run_id, True)
        return LocalLock(path, run_id, False)


def backend(config: RuntimeConfig) -> RuntimeBackend:
    return LocalBackend(config.root)
