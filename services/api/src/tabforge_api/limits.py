"""Abuse limits (threat model T3): per-user write rate and daily upload quota.

The rate limiter keeps its state in process memory: with several API replicas each one counts
separately (the effective limit multiplies by the replica count). Good enough for the MVP's
single instance; a shared store (Postgres or Redis) is the step up when scaling out.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(
        self, max_events: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._max = max_events
        self._window = window_s
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record an event; return None if allowed, else seconds until the next one is."""
        now = self._clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= now - self._window:
                events.popleft()
            if len(events) >= self._max:
                return max(1, math.ceil(events[0] + self._window - now))
            events.append(now)
            return None
