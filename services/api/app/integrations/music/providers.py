"""Music search through official catalogues. Nexora only returns official links, 30-second
previews or embeds. It never downloads or re-hosts audio.

* Spotify Web API (client-credentials search + official embed player) when configured.
* Apple iTunes Search API (no key; returns Apple Music links and official previews) otherwise.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.exceptions import UpstreamError
from app.integrations.base import TTLCache, fetch_json


class MusicResult(BaseModel):
    id: str
    provider: str
    kind: str  # track | playlist | album
    title: str
    artist: str | None = None
    album: str | None = None
    artwork_url: str | None = None
    url: str
    embed_url: str | None = None
    preview_url: str | None = None
    duration_ms: int | None = None


class ITunesMusicProvider:
    name = "itunes"

    def __init__(self, http: httpx.AsyncClient, country: str = "IN", timeout: float = 10.0) -> None:
        self.http = http
        self.country = country
        self.timeout = timeout
        self.cache = TTLCache(ttl_seconds=3600)

    async def search(self, query: str, limit: int = 10) -> list[MusicResult]:
        key = f"{query.lower()}:{limit}"
        if (cached := self.cache.get(key)) is not None:
            return cached
        data = await fetch_json(
            self.http,
            "GET",
            "https://itunes.apple.com/search",
            provider="Apple iTunes Search",
            params={
                "term": query[:150],
                "media": "music",
                "entity": "song",
                "limit": max(1, min(limit, 25)),
                "country": self.country,
            },
            timeout=self.timeout,
        )
        results = [
            MusicResult(
                id=str(item.get("trackId")),
                provider=self.name,
                kind="track",
                title=item.get("trackName", ""),
                artist=item.get("artistName"),
                album=item.get("collectionName"),
                artwork_url=item.get("artworkUrl100"),
                url=item.get("trackViewUrl", ""),
                preview_url=item.get("previewUrl"),
                duration_ms=item.get("trackTimeMillis"),
            )
            for item in data.get("results", [])
            if item.get("trackViewUrl")
        ]
        self.cache.set(key, results)
        return results


class SpotifyMusicProvider:
    name = "spotify"

    def __init__(
        self, http: httpx.AsyncClient, client_id: str, client_secret: str, market: str = "IN", timeout: float = 10.0
    ) -> None:
        self.http = http
        self.client_id = client_id
        self.client_secret = client_secret
        self.market = market
        self.timeout = timeout
        self._token: str | None = None
        self._token_expiry = 0.0
        self.cache = TTLCache(ttl_seconds=3600)

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        data = await fetch_json(
            self.http,
            "POST",
            "https://accounts.spotify.com/api/token",
            provider="Spotify",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"},
            timeout=self.timeout,
        )
        token = data.get("access_token")
        if not token:
            raise UpstreamError("Spotify did not return an access token")
        self._token = token
        self._token_expiry = time.monotonic() + int(data.get("expires_in", 3600))
        return token

    async def search(self, query: str, limit: int = 10) -> list[MusicResult]:
        key = f"{query.lower()}:{limit}"
        if (cached := self.cache.get(key)) is not None:
            return cached
        token = await self._access_token()
        data = await fetch_json(
            self.http,
            "GET",
            "https://api.spotify.com/v1/search",
            provider="Spotify",
            params={"q": query[:150], "type": "track,playlist", "limit": max(1, min(limit, 20)), "market": self.market},
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        results: list[MusicResult] = []
        for pl in ((data.get("playlists") or {}).get("items") or [])[:3]:
            if not pl:
                continue
            results.append(
                self._result(
                    pl,
                    "playlist",
                    pl.get("name", ""),
                    (pl.get("owner") or {}).get("display_name"),
                    None,
                    pl.get("images"),
                )
            )
        for tr in (data.get("tracks") or {}).get("items") or []:
            artists = ", ".join(a.get("name", "") for a in tr.get("artists") or [])
            album = tr.get("album") or {}
            res = self._result(tr, "track", tr.get("name", ""), artists, album.get("name"), album.get("images"))
            res.duration_ms = tr.get("duration_ms")
            results.append(res)
        self.cache.set(key, results)
        return results

    def _result(
        self,
        item: dict[str, Any],
        kind: str,
        title: str,
        artist: str | None,
        album: str | None,
        images: list[dict[str, Any]] | None,
    ) -> MusicResult:
        sid = item.get("id", "")
        return MusicResult(
            id=sid,
            provider=self.name,
            kind=kind,
            title=title,
            artist=artist,
            album=album,
            artwork_url=(images or [{}])[0].get("url") if images else None,
            url=(item.get("external_urls") or {}).get("spotify", f"https://open.spotify.com/{kind}/{sid}"),
            embed_url=f"https://open.spotify.com/embed/{kind}/{sid}",
        )


MusicProvider = ITunesMusicProvider | SpotifyMusicProvider
