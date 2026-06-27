"""In-memory rate limiter using a sliding-window counter.

No external dependencies (no Redis).  Thread-safe for asyncio usage
when called from the same event-loop thread (which is the normal
MergeMate agent path).
"""

from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    """Sliding-window rate limiter keyed by arbitrary strings."""

    def __init__(
        self,
        max_requests: int = 30,
        window_seconds: float = 60.0,
    ) -> None:
        """Configure the limiter.

        Args:
            max_requests: Maximum requests allowed within the window.
            window_seconds: Size of the sliding window in seconds.
        """
        self._max_requests = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, key: str, cost: int = 1) -> bool:
        """Return ``True`` if the request for *key* is within limits.

        The request is recorded on success — if you need a peek-only
        check, call :meth:`check` instead.
        """
        self._prune(key)
        if self._count(key) + cost > self._max_requests:
            return False
        self._record(key, cost)
        return True

    def check(self, key: str, cost: int = 1) -> bool:
        """Peek whether the next request would be allowed without recording it."""
        self._prune(key)
        return self._count(key) + cost <= self._max_requests

    def remaining(self, key: str) -> int:
        """Return remaining capacity for *key*."""
        self._prune(key)
        return max(0, self._max_requests - self._count(key))

    def reset(self, key: str) -> None:
        """Clear all state for *key*."""
        self._buckets.pop(key, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune(self, key: str) -> None:
        """Drop timestamps that have fallen outside the window."""
        now = time.monotonic()
        cutoff = now - self._window
        bucket = self._buckets.get(key)
        if bucket is None:
            return
        # Keep only timestamps > cutoff.
        self._buckets[key] = [ts for ts in bucket if ts > cutoff]
        if not self._buckets[key]:
            del self._buckets[key]

    def _count(self, key: str) -> int:
        """Return current number of recorded timestamps for *key*."""
        return len(self._buckets.get(key, ()))

    def _record(self, key: str, cost: int) -> None:
        """Add *cost* timestamps for *key* at the current instant."""
        now = time.monotonic()
        # Small cost → extend with repeated timestamps; high cost would
        # be unusual for our usage profile.
        self._buckets[key].extend([now] * cost)
