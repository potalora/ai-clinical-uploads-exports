from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from app.config import settings


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed for the given key."""
        now = time.monotonic()
        with self._lock:
            # Remove expired entries
            self._requests[key] = [
                t for t in self._requests[key]
                if now - t < self.window_seconds
            ]
            if len(self._requests[key]) >= self.max_requests:
                return False
            self._requests[key].append(now)
            return True


login_limiter = RateLimiter(
    max_requests=settings.login_rate_limit,
    window_seconds=settings.login_rate_window,
)
register_limiter = RateLimiter(
    max_requests=settings.register_rate_limit,
    window_seconds=settings.register_rate_window,
)
