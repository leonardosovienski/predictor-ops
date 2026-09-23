from __future__ import annotations

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import RuntimeConfig


@contextmanager
def _mutation_guard(path: Path):
    """Serialize ownership checks and mutations on a persistent OS-locked inode.

    The guard is never unlinked. OS locks are released when a process dies,
    avoiding a second stale-file takeover protocol around the lease itself.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            # Initialize through an unbuffered descriptor. Windows byte locks are
            # mandatory: when a concurrent process already initialized the guard and
            # holds byte 0, the write is refused; the lock loop below then waits for
            # it. A buffered write would re-raise on seek/close (SHARED-005).
            descriptor = os.open(path, os.O_WRONLY)
            try:
                os.write(descriptor, b"0")
            except PermissionError:
                pass
            finally:
                os.close(descriptor)
        deadline = time.monotonic() + 30
        while True:
            try:
                handle.seek(0)
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("lock mutation guard timeout") from None
                time.sleep(0.01)
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        with _mutation_guard(self.path.with_name(".mutation.guard")):
            if not self._acquired or not self._owned():
                return False
            os.utime(self.path, None)
            return True

    def release(self) -> None:
        with _mutation_guard(self.path.with_name(".mutation.guard")):
            if self._acquired and self._owned():
                self.path.unlink(missing_ok=True)
            self._acquired = False


class LocalBackend:
    def __init__(self, root: Path) -> None:
        self.root = root

    def acquire(self, job_id: str, run_id: str, ttl: float) -> LocalLock:
        with _mutation_guard(self.root / job_id / ".mutation.guard"):
            return self._acquire(job_id, run_id, ttl)

    def _acquire(self, job_id: str, run_id: str, ttl: float) -> LocalLock:
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
