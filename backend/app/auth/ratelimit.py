"""Login throttling: failures per client address and per email in a sliding window.

In-process state, adequate for the single local API process of this release;
a multi-process deployment needs a shared store (Redis) behind the same API.
"""
from __future__ import annotations

from collections import defaultdict, deque
import threading
import time


class LoginLimiter:
    def __init__(self, max_failures: int, window_seconds: int, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window_seconds
        self.clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        bucket = self._failures[key]
        while bucket and bucket[0] <= now - self.window:
            bucket.popleft()
        return bucket

    def retry_after(self, *keys: str) -> int:
        """Seconds until a blocked key frees up; 0 when the attempt may proceed."""
        now = self.clock()
        with self._lock:
            waits = [int(bucket[0] + self.window - now) + 1 for key in keys
                     if len(bucket := self._recent(key, now)) >= self.max_failures]
        return max(waits, default=0)

    def failure(self, *keys: str) -> None:
        now = self.clock()
        with self._lock:
            for key in keys:
                self._recent(key, now).append(now)

    def success(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)
