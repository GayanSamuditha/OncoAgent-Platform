import threading
import time

import pytest

from app.performance.limits import BoundedCapacity, CapacityUnavailable


def test_capacity_starts_empty_and_releases() -> None:
    capacity = BoundedCapacity(1, "test")
    assert capacity.snapshot() == {"capacity": 1, "active": 0, "queued": 0, "available": 1}
    with capacity.acquire(0.1) as wait:
        assert wait >= 0
        assert capacity.active == 1
    assert capacity.snapshot()["active"] == 0


def test_exception_releases_capacity() -> None:
    capacity = BoundedCapacity(1, "test")
    with pytest.raises(RuntimeError):
        with capacity.acquire(0.1):
            raise RuntimeError("bounded test failure")
    assert capacity.active == 0


def test_timeout_does_not_leak_queued_capacity() -> None:
    capacity = BoundedCapacity(1, "test")
    with capacity.acquire(0.1):
        with pytest.raises(CapacityUnavailable):
            with capacity.acquire(0.01):
                pass
        assert capacity.queued == 0
    assert capacity.snapshot()["available"] == 1


def test_concurrent_waiter_is_released_after_owner() -> None:
    capacity = BoundedCapacity(1, "test")
    entered = threading.Event()
    finished = threading.Event()

    def waiter() -> None:
        with capacity.acquire(0.5):
            entered.set()
        finished.set()

    with capacity.acquire(0.1):
        thread = threading.Thread(target=waiter)
        thread.start()
        time.sleep(0.01)
        assert capacity.queued == 1
    assert entered.wait(0.2)
    assert finished.wait(0.2)
    thread.join(timeout=0.2)
    assert capacity.snapshot()["active"] == 0


def test_reset_rejects_busy_capacity() -> None:
    capacity = BoundedCapacity(1, "test")
    with capacity.acquire(0.1):
        with pytest.raises(RuntimeError):
            capacity.reset(2)
    capacity.reset(2)
    assert capacity.capacity == 2
