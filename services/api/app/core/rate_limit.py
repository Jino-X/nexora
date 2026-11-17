"""Sliding-window rate limiter.

In-process by design for a single API instance. When running several instances, put the same
interface on Redis (INCR + EXPIRE per window) - see docs/deployment.md."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.exceptions import RateLimitedError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, int(window_seconds - (now - hits[0])))
            raise RateLimitedError("Too many requests, please slow down", details={"retry_after_seconds": retry})
        hits.append(now)
        if now - self._last_sweep > 300:
            self._sweep(now, window_seconds)

    def _sweep(self, now: float, window_seconds: float) -> None:
        self._last_sweep = now
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > window_seconds]:
            del self._hits[key]
