"""Shared fixtures: isolated SQLite database per test, mocked external HTTP, dev-token auth."""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.core.security import dev_user_id, issue_dev_token
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, TokenCallback, ToolCall, Usage
from app.llm.factory import FallbackLLM
from app.main import create_app
from app.services import Services, build_services, close_services

KEY_1 = base64.b64encode(b"\x01" * 32).decode()
KEY_2 = base64.b64encode(b"\x02" * 32).decode()
INTERNAL_KEY = "internal-test-key-0123456789"


def make_settings(tmp_path: Any, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": f"sqlite+aiosqlite:///{tmp_path}/nexora-test.db",
        "auth_dev_mode": True,
        "dev_jwt_secret": "dev-secret-for-tests-0123456789abcdef",
        "internal_service_key": INTERNAL_KEY,
        "vault_master_keys": f"k1:{KEY_1}",
        "vault_active_key_id": "k1",
        "llm_provider": "offline",
        "llm_fallback_providers": [],
        "embedding_provider": "hashing",
        "run_scheduler_in_api": False,
        "log_json": False,
        "log_level": "WARNING",
        "livekit_url": "wss://nexora-test.livekit.cloud",
        "livekit_api_key": "APItestkey",
        "livekit_api_secret": "livekit-test-secret-0123456789abcdef",
        "google_client_id": "google-client-id",
        "google_client_secret": "google-client-secret",
        "youtube_api_key": "yt-test-key",
        "whatsapp_app_secret": "wa-app-secret",
        "whatsapp_webhook_verify_token": "wa-verify",
        "news_feeds": [{"name": "Test Feed", "url": "https://news.example.com/rss", "category": "technology"}],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


# ---- mocked external HTTP ---------------------------------------------------------------------

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>
<item><title>Open model beats benchmark</title><link>https://news.example.com/a?utm_source=x</link>
<pubDate>Fri, 13 Nov 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Big <b>news</b>&lt;/p&gt;</description></item>
<item><title>Open model beats the benchmark</title><link>https://news.example.com/a</link></item>
<item><title>Chennai metro expands</title><link>https://news.example.com/b</link>
<pubDate>Fri, 13 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""

WEATHER = {
    "timezone": "Asia/Kolkata",
    "current": {
        "time": "2026-11-14T10:00",
        "temperature_2m": 29.4,
        "relative_humidity_2m": 70,
        "apparent_temperature": 33.0,
        "precipitation": 0.0,
        "weather_code": 2,
        "wind_speed_10m": 12.0,
        "is_day": 1,
    },
    "daily": {
        "time": ["2026-11-14", "2026-11-15"],
        "weather_code": [61, 3],
        "temperature_2m_max": [31, 30],
        "temperature_2m_min": [24, 23],
        "precipitation_probability_max": [60, 20],
        "precipitation_sum": [4.2, 0.0],
        "wind_speed_10m_max": [18, 15],
        "sunrise": ["2026-11-14T06:05", "2026-11-15T06:05"],
        "sunset": ["2026-11-14T17:45", "2026-11-15T17:45"],
    },
}

OVERPASS = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 13.0850,
            "lon": 80.2710,
            "tags": {"name": "Indian Oil", "amenity": "fuel", "opening_hours": "24/7"},
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 13.0900, "lon": 80.2800},
            "tags": {"brand": "HP", "amenity": "fuel"},
        },
    ]
}


@dataclass
class MockHTTP:
    calls: list[httpx.Request] = field(default_factory=list)
    overrides: dict[str, Callable[[httpx.Request], httpx.Response]] = field(default_factory=dict)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = str(request.url)
        for prefix, fn in self.overrides.items():
            if url.startswith(prefix):
                return fn(request)
        host, path = request.url.host, request.url.path
        if host == "api.open-meteo.com":
            return httpx.Response(200, json=WEATHER)
        if host in ("overpass-api.de", "maps.mail.ru"):
            return httpx.Response(200, json=OVERPASS)
        if host == "nominatim.openstreetmap.org" and path == "/search":
            return httpx.Response(
                200,
                json=[
                    {"display_name": "Chennai, Tamil Nadu, India", "lat": "13.0827", "lon": "80.2707", "type": "city"}
                ],
            )
        if host == "nominatim.openstreetmap.org" and path == "/reverse":
            return httpx.Response(200, json={"display_name": "Chennai, Tamil Nadu, India"})
        if host == "news.example.com":
            return httpx.Response(200, content=RSS, headers={"content-type": "application/rss+xml"})
        if host == "itunes.apple.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "trackId": 1,
                            "trackName": "Calm Piano",
                            "artistName": "A",
                            "trackViewUrl": "https://music.apple.com/x",
                            "previewUrl": "https://audio-ssl.itunes.apple.com/p.m4a",
                        }
                    ]
                },
            )
        if host == "www.googleapis.com" and path.startswith("/youtube"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": {"videoId": "abc123"},
                            "snippet": {"title": "React in 100 seconds", "channelTitle": "Fireship"},
                        }
                    ]
                },
            )
        if host == "localhost" and request.url.port == 11434:
            raise httpx.ConnectError("ollama down", request=request)
        return httpx.Response(404, json={"error": "unmocked", "url": url})


@pytest.fixture
def mock_http() -> MockHTTP:
    return MockHTTP()


@pytest.fixture
def settings(tmp_path: Any) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def services(settings: Settings, mock_http: MockHTTP) -> AsyncIterator[Services]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(mock_http.handler))
    svc = await build_services(settings, http=http)
    yield svc
    await close_services(svc)


@pytest.fixture
async def client(settings: Settings, services: Services) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, services)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


def auth_headers(settings: Settings, email: str = "alice@example.com") -> dict[str, str]:
    token, _ = issue_dev_token(settings, dev_user_id(email), email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alice(settings: Settings) -> dict[str, str]:
    return auth_headers(settings, "alice@example.com")


@pytest.fixture
def bob(settings: Settings) -> dict[str, str]:
    return auth_headers(settings, "bob@example.com")


def user_id(email: str) -> uuid.UUID:
    return dev_user_id(email)


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            events.append((name, data or {}))
    return events


# ---- scripted LLM -------------------------------------------------------------------------------


class ScriptedLLM(LLMProvider):
    """Returns queued responses in order; records every request."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, script: list[LLMResponse | Exception]) -> None:
        self.script = list(script)
        self.requests: list[tuple[list[ChatMessage], list[dict[str, Any]] | None]] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: TokenCallback | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.requests.append((list(messages), tools))
        item = self.script.pop(0) if self.script else LLMResponse("Done.", [], self.name, self.model)
        if isinstance(item, Exception):
            raise item
        if item.content and on_token:
            for word in item.content.split(" "):
                await on_token(word + " ")
        return item


def say(text: str) -> LLMResponse:
    return LLMResponse(content=text, tool_calls=[], provider="scripted", model="scripted-1", usage=Usage(10, 5))


def call(name: str, **args: Any) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(id=uuid.uuid4().hex[:8], name=name, arguments=args)],
        provider="scripted",
        model="scripted-1",
        usage=Usage(10, 5),
    )


class FakeRouter:
    def __init__(self, provider: LLMProvider) -> None:
        self.chain_obj = FallbackLLM([provider])
        self.names = [provider.name]

    def chain(self, mode: str = "auto") -> FallbackLLM:
        return self.chain_obj

    def provider(self, name: str) -> LLMProvider | None:
        return self.chain_obj.providers[0]


def use_llm(services: Services, *script: LLMResponse | Exception) -> ScriptedLLM:
    llm = ScriptedLLM(list(script))
    services.llm = FakeRouter(llm)  # type: ignore[assignment]
    return llm


os.environ.setdefault("TZ", "UTC")
