import json
import multiprocessing
import os
import time

from predictor_ops.models import RuntimeConfig
from predictor_ops.runtime import LocalBackend, append_jsonl, atomic_json, backend


def _local_racer(root, barrier, queue, token):
    barrier.wait()
    lock = LocalBackend(root).acquire("race", token, 60)
    queue.put(lock.acquired)
    time.sleep(0.2)
    if lock.acquired:
        lock.release()


def test_local_lock_exclusion_release_and_stale(tmp_path):
    local = LocalBackend(tmp_path)
    first = local.acquire("job", "one", 60)
    assert first.acquired and first.refresh()
    assert not local.acquire("job", "two", 60).acquired
    first.release()
    stale = local.acquire("job", "old", 60)
    assert stale.acquired
    os.utime(stale.path, (time.time() - 61, time.time() - 61))
    replacement = local.acquire("job", "new", 60)
    assert replacement.acquired
    stale.release()
    assert replacement.refresh()
    replacement.release()


def test_local_lock_has_one_winner_across_processes(tmp_path):
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_local_racer, args=(tmp_path, barrier, queue, token)) for token in ("a", "b")]
    for process in processes:
        process.start()
    assert sum(queue.get(timeout=5) for _ in processes) == 1
    for process in processes:
        process.join(5)
        assert process.exitcode == 0


def test_factory_is_local_only(tmp_path):
    assert isinstance(backend(RuntimeConfig(root=tmp_path)), LocalBackend)


def test_stale_takeover_has_one_winner_across_processes(tmp_path):
    old = LocalBackend(tmp_path).acquire("race", "expired", 60)
    os.utime(old.path, (time.time() - 61, time.time() - 61))
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_local_racer, args=(tmp_path, barrier, queue, token)) for token in ("a", "b")]
    for process in processes:
        process.start()
    assert sum(queue.get(timeout=10) for _ in processes) == 1
    assert not old.refresh()
    old.release()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0


def test_atomic_json_and_durable_jsonl(tmp_path):
    heartbeat, events = tmp_path / "heartbeat.json", tmp_path / "events.jsonl"
    atomic_json(heartbeat, {"ok": True})
    append_jsonl(events, {"n": 1})
    append_jsonl(events, {"n": 2})
    assert json.loads(heartbeat.read_text()) == {"ok": True}
    assert [json.loads(line)["n"] for line in events.read_text().splitlines()] == [1, 2]


def _hold_first_byte(path, ready, release):
    with open(path, "a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready.set()
        release.wait(10)


def test_empty_guard_locked_by_another_process_waits_instead_of_crashing(tmp_path):
    """SHARED-005: two processes race on a new job's guard; the loser must wait, not die.

    Windows locks are mandatory: initializing the guard with a buffered write while the
    winner already holds byte 0 raised PermissionError out of LocalBackend.acquire.
    """
    import threading

    from predictor_ops.runtime import _mutation_guard

    guard = tmp_path / "job" / ".mutation.guard"
    guard.parent.mkdir()
    guard.write_bytes(b"")
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    holder = context.Process(target=_hold_first_byte, args=(str(guard), ready, release))
    holder.start()
    assert ready.wait(10)
    threading.Timer(0.5, release.set).start()
    started = time.monotonic()
    with _mutation_guard(guard):
        waited = time.monotonic() - started
    holder.join(10)
    assert holder.exitcode == 0
    assert waited >= 0.3  # it really waited for the holder
