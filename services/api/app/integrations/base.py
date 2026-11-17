"""Shared helpers for provider adapters: bounded TTL cache, JSON fetch with uniform errors."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

import httpx

from app.core.exceptions import UpstreamError


class TTLCache:
    """Small in-process LRU+TTL cache for non-sensitive provider responses (weather, places, news)."""

    def __init__(self, ttl_seconds: float, max_items: int = 512) -> None:
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.monotonic() + self.ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)


async def fetch_json(
    http: httpx.AsyncClient, method: str, url: str, *, provider: str, timeout: float = 12.0, **kwargs: Any
) -> Any:
    try:
        res = await http.request(method, url, timeout=timeout, **kwargs)
    except httpx.TimeoutException as exc:
        raise UpstreamError(f"{provider} timed out", code="upstream_timeout") from exc
    except httpx.HTTPError as exc:
        raise UpstreamError(f"{provider} is unreachable") from exc
    if res.status_code == 429:
        raise UpstreamError(f"{provider} rate limit reached, try again later", code="upstream_rate_limited")
    if res.status_code >= 400:
        raise UpstreamError(f"{provider} returned an error ({res.status_code})", details={"status": res.status_code})
    try:
        return res.json()
    except ValueError as exc:
        raise UpstreamError(f"{provider} returned an invalid response") from exc


def round_coord(value: float, places: int = 3) -> float:
    """~110 m buckets, used for cache keys so nearby requests share results."""
    return round(value, places)
