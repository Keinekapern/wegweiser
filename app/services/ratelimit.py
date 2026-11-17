import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Ensures at least `min_interval` seconds between calls, across all threads."""

    def __init__(self, min_interval: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = self._next_allowed - self._clock()
            if delay > 0:
                self._sleep(delay)
            self._next_allowed = self._clock() + self.min_interval
