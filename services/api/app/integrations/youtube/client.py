"""YouTube Data API v3 adapter (official API, API key). search.list costs 100 quota units per call,
against a default daily quota of 10,000, so results are cached for an hour."""

from __future__ import annotations

import html
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.core.exceptions import NotConfiguredError
from app.integrations.base import TTLCache, fetch_json

API = "https://www.googleapis.com/youtube/v3"


class YouTubeResult(BaseModel):
    id: str
    kind: Literal["video", "channel", "playlist"]
    title: str
    description: str | None = None
    channel_title: str | None = None
    published_at: str | None = None
    thumbnail_url: str | None = None
    url: str
    embed_url: str | None = None


class YouTubeProvider:
    def __init__(self, http: httpx.AsyncClient, api_key: str | None, timeout: float = 10.0) -> None:
        self.http = http
        self.api_key = api_key
        self.timeout = timeout
        self.cache = TTLCache(ttl_seconds=3600, max_items=256)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        *,
        kind: Literal["video", "channel", "playlist"] = "video",
        max_results: int = 8,
        region: str | None = None,
    ) -> list[YouTubeResult]:
        if not self.api_key:
            raise NotConfiguredError("YouTube search needs YOUTUBE_API_KEY", code="youtube_not_configured")
        query = query.strip()[:200]
        key = f"{kind}:{region}:{max_results}:{query.lower()}"
        if (cached := self.cache.get(key)) is not None:
            return cached
        params: dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": kind,
            "maxResults": max(1, min(max_results, 25)),
            "safeSearch": "moderate",
            "key": self.api_key,
        }
        if region:
            params["regionCode"] = region
        data = await fetch_json(
            self.http, "GET", f"{API}/search", provider="YouTube", params=params, timeout=self.timeout
        )
        results = [r for r in (self._parse(item) for item in data.get("items", [])) if r]
        self.cache.set(key, results)
        return results

    @staticmethod
    def _parse(item: dict[str, Any]) -> YouTubeResult | None:
        ident = item.get("id") or {}
        snippet = item.get("snippet") or {}
        thumbs = snippet.get("thumbnails") or {}
        thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        base = {
            "title": html.unescape(snippet.get("title", "")),
            "description": html.unescape(snippet.get("description", "")) or None,
            "channel_title": snippet.get("channelTitle"),
            "published_at": snippet.get("publishedAt"),
            "thumbnail_url": thumb,
        }
        if vid := ident.get("videoId"):
            return YouTubeResult(
                id=vid,
                kind="video",
                url=f"https://www.youtube.com/watch?v={vid}",
                embed_url=f"https://www.youtube-nocookie.com/embed/{vid}",
                **base,
            )
        if cid := ident.get("channelId"):
            return YouTubeResult(id=cid, kind="channel", url=f"https://www.youtube.com/channel/{cid}", **base)
        if pid := ident.get("playlistId"):
            return YouTubeResult(
                id=pid,
                kind="playlist",
                url=f"https://www.youtube.com/playlist?list={pid}",
                embed_url=f"https://www.youtube-nocookie.com/embed/videoseries?list={pid}",
                **base,
            )
        return None
