import json
import multiprocessing
import os
import time

import fakeredis

from predictor_ops.models import RuntimeConfig
from predictor_ops.runtime import LocalBackend, RedisBackend, append_jsonl, atomic_json, backend


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


def test_redis_lock_ownership_and_factory(tmp_path):
    client = fakeredis.FakeRedis(decode_responses=True)
    redis = RedisBackend("redis://unused", "test", client)
    first = redis.acquire("job", "one", 60)
    assert first.acquired and first.refresh()
    assert not redis.acquire("job", "two", 60).acquired
    first.release()
    assert redis.acquire("job", "two", 60).acquired
    config = RuntimeConfig(backend="redis", redis_url="redis://unused", root=tmp_path)
    assert isinstance(backend(config, redis_client=client), RedisBackend)


def test_atomic_json_and_durable_jsonl(tmp_path):
    heartbeat, events = tmp_path / "heartbeat.json", tmp_path / "events.jsonl"
    atomic_json(heartbeat, {"ok": True})
    append_jsonl(events, {"n": 1})
    append_jsonl(events, {"n": 2})
    assert json.loads(heartbeat.read_text()) == {"ok": True}
    assert [json.loads(line)["n"] for line in events.read_text().splitlines()] == [1, 2]
