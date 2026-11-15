from __future__ import annotations

import threading
import time


class RateLimiter:
    """Single-consumer RPM limiter. Discovery concurrency is 1."""

    def __init__(self, max_rpm: int = 30) -> None:
        self.max_rpm = max_rpm
        self.min_interval = 60.0 / max(max_rpm, 1)
        self._lock = threading.Lock()
        self._last = 0.0
        self.wait_count = 0
        self.total_wait_s = 0.0

    def acquire(self) -> float:
        with self._lock:
            now = time.monotonic()
            wait = self._last + self.min_interval - now
            if wait > 0:
                self.wait_count += 1
                self.total_wait_s += wait
                time.sleep(wait)
            self._last = time.monotonic()
            return max(wait, 0.0)
