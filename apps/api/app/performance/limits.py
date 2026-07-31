"""Resettable, bounded in-process capacity gates for local workloads."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import get_settings
from app.observability.metrics import (
    PERFORMANCE_QUEUE_DEPTH,
    PERFORMANCE_WORKFLOW_CONCURRENCY,
    observe,
)


class CapacityUnavailable(RuntimeError):
    """The bounded local capacity was busy for the configured wait period."""


class BoundedCapacity:
    """A resettable capacity gate with explicit ownership accounting.

    The condition and counters are process-local by design.  Resetting is only
    used during API startup/tests; it never persists capacity across a process
    boundary.  A lease releases exactly once, including exceptions.
    """

    def __init__(self, capacity: int, name: str) -> None:
        self.name = name
        self._condition = threading.Condition()
        self._capacity = 0
        self._active = 0
        self._queued = 0
        self.reset(capacity)

    @property
    def capacity(self) -> int:
        with self._condition:
            return self._capacity

    @property
    def active(self) -> int:
        with self._condition:
            return self._active

    @property
    def queued(self) -> int:
        with self._condition:
            return self._queued

    def _observe(self) -> None:
        if self.name == "workflow":
            observe(
                PERFORMANCE_WORKFLOW_CONCURRENCY,
                float(self._active),
                {"framework": "workflow"},
            )
        observe(PERFORMANCE_QUEUE_DEPTH, float(self._queued), {"queue": self.name})

    def reset(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        with self._condition:
            if self._active or self._queued:
                raise RuntimeError(f"cannot reset busy capacity gate: {self.name}")
            self._capacity = capacity
            self._observe()

    def snapshot(self) -> dict[str, int]:
        with self._condition:
            return {
                "capacity": self._capacity,
                "active": self._active,
                "queued": self._queued,
                "available": self._capacity - self._active,
            }

    @contextmanager
    def acquire(self, timeout_seconds: float) -> Iterator[float]:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        started = time.perf_counter()
        deadline = started + timeout_seconds
        acquired = False
        with self._condition:
            self._queued += 1
            self._observe()
            try:
                while self._active >= self._capacity:
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0 or not self._condition.wait(timeout=remaining):
                        raise CapacityUnavailable(self.name)
                self._active += 1
                acquired = True
                self._observe()
            finally:
                self._queued -= 1
                self._observe()
        try:
            yield time.perf_counter() - started
        finally:
            if acquired:
                with self._condition:
                    if self._active <= 0:
                        raise RuntimeError(f"capacity release underflow: {self.name}")
                    self._active -= 1
                    self._observe()
                    self._condition.notify()


_workflow_capacity = BoundedCapacity(get_settings().api_workflow_concurrency, "workflow")


def workflow_capacity() -> BoundedCapacity:
    return _workflow_capacity


def reset_workflow_capacity(capacity: int | None = None) -> None:
    """Reset startup/test capacity after the process has no active leases."""

    _workflow_capacity.reset(capacity or get_settings().api_workflow_concurrency)
