import multiprocessing
import os
import time

from redis import Redis

from predictor_ops.runtime import RedisBackend

URL = os.environ["PREDICTOR_OPS_TEST_REDIS_URL"]


def _acquire(barrier, queue, token):
    backend = RedisBackend(URL, "integration")
    barrier.wait()
    lock = backend.acquire("race", token, 2)
    queue.put((token, lock.acquired))
    time.sleep(0.2)
    if lock.acquired:
        lock.release()


def test_two_processes_have_exactly_one_winner():
    Redis.from_url(URL).flushdb()
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_acquire, args=(barrier, queue, token)) for token in ("one", "two")]
    for process in processes:
        process.start()
    results = [queue.get(timeout=5) for _ in processes]
    for process in processes:
        process.join(5)
        assert process.exitcode == 0
    assert sum(acquired for _, acquired in results) == 1


def test_ttl_ownership_delayed_release_refresh_and_isolation():
    client = Redis.from_url(URL, decode_responses=True)
    client.flushdb()
    backend = RedisBackend(URL, "integration")
    old = backend.acquire("ttl", "old", 0.2)
    assert old.acquired and 0 < client.pttl("integration:lock:ttl") <= 200
    time.sleep(0.3)
    new = backend.acquire("ttl", "new", 2)
    assert new.acquired
    assert not old.refresh()
    old.release()
    assert new.refresh() and client.get("integration:lock:ttl") == "new"
    assert backend.acquire("other-job", "other", 2).acquired
    new.release()


def test_disconnect_reconnect_and_wrong_client_cannot_release():
    first_client = Redis.from_url(URL, decode_responses=True)
    first_client.flushdb()
    backend = RedisBackend(URL, "integration", first_client)
    lock = backend.acquire("network", "owner", 2)
    assert lock.acquired
    wrong = RedisBackend(URL, "integration").acquire("network", "wrong", 2)
    assert not wrong.acquired
    wrong.release()
    assert first_client.get("integration:lock:network") == "owner"
    first_client.connection_pool.disconnect()
    assert lock.refresh()
    lock.release()
