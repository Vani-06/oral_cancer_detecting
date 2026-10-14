import time
from collections import defaultdict, deque
from threading import Lock


class LoginRateLimiter:
    """Locks out an (IP, email) pair after repeated failed logins.

    In-memory and per process: enough to stop online password guessing
    against a single API instance. Behind several workers or replicas, move
    this to a shared store (e.g. Redis) or enforce it at the reverse proxy.
    """

    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        return attempts

    def retry_after(self, ip: str, email: str) -> int | None:
        """Seconds until the next attempt is allowed, or None if not locked."""
        key = (ip, email)
        with self._lock:
            now = time.monotonic()
            attempts = self._prune(key, now)
            if len(attempts) < self.max_failures:
                return None
            return max(1, int(self.window_seconds - (now - attempts[0])) + 1)

    def record_failure(self, ip: str, email: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune((ip, email), now).append(now)

    def reset(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop((ip, email), None)
