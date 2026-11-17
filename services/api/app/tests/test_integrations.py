"""Provider adapters: parsing, failure handling, OAuth, encrypted credentials, webhooks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.core.exceptions import NotConfiguredError, UpstreamError, ValidationFailedError
from app.database import models as m
from app.database.session import session_scope
from app.integrations.gmail.client import build_raw_email, extract_body
from app.integrations.maps.osm import OSMPlacesProvider, normalize_category
from app.integrations.news.rss import canonical_link, dedupe, parse_feed
from app.integrations.whatsapp.client import normalize_phone, verify_webhook_signature
from app.integrations.youtube.client import YouTubeProvider
from app.tests.conftest import RSS, user_id


async def test_weather_parsing_and_cache(services, mock_http):
    report = await services.weather.forecast(13.08, 80.27)
    assert report.current.description == "Partly cloudy" and report.daily[0].description == "Slight rain"
    await services.weather.forecast(13.08, 80.27)
    assert sum(1 for c in mock_http.calls if c.url.host == "api.open-meteo.com") == 1


async def test_external_timeout_maps_to_upstream_error(services, mock_http):
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)

    mock_http.overrides["https://api.open-meteo.com"] = boom
    with pytest.raises(UpstreamError) as exc:
        await services.weather.forecast(10.0, 76.0)
    assert exc.value.code == "upstream_timeout"


async def test_weather_api_endpoint_requires_location(client, alice):
    res = await client.get("/api/v1/weather", headers=alice)
    assert res.status_code == 422 and res.json()["error"]["code"] == "location_required"
    res = await client.get("/api/v1/weather?lat=13.08&lon=80.27", headers=alice)
    assert res.status_code == 200 and res.json()["attribution"].startswith("Weather data by Open-Meteo")


def test_overpass_query_and_categories():
    q = OSMPlacesProvider.build_overpass_query("hotel", 13.0, 80.0, 2000, 5)
    assert 'nwr["tourism"="hotel"](around:2000,13.000000,80.000000)' in q and "out center tags 15" in q
    assert normalize_category("petrol") == "petrol_pump"
    with pytest.raises(ValidationFailedError):
        normalize_category("casino")


async def test_nearby_sorted_with_directions(services):
    places = await services.places.nearby("petrol_pump", 13.0827, 80.2707)
    assert [p.name for p in places] == ["Indian Oil", "HP"]
    assert places[0].distance_m < places[1].distance_m
    assert places[0].directions_url.startswith("https://www.google.com/maps/dir/?api=1&destination=")


def test_rss_parse_and_dedupe():
    items = parse_feed(RSS, "Test", "technology")
    assert items[0].summary == "Big news"
    assert len(dedupe(items)) == 2
    assert canonical_link("https://X.com/a/?utm_source=t&id=1") == "https://x.com/a?id=1"


async def test_news_endpoint(client, alice):
    res = await client.get("/api/v1/news?category=technology", headers=alice)
    titles = [i["title"] for i in res.json()]
    assert titles == ["Open model beats benchmark", "Chennai metro expands"]


async def test_youtube_not_configured_and_configured(services):
    with pytest.raises(NotConfiguredError):
        await YouTubeProvider(services.http, None).search("react")
    results = await services.youtube.search("react tutorials")
    assert results[0].embed_url == "https://www.youtube-nocookie.com/embed/abc123"


async def test_music_itunes(client, alice):
    res = await client.get("/api/v1/music/search?q=relaxing", headers=alice)
    assert res.json()[0]["preview_url"].startswith("https://")


def test_email_helpers():
    raw = build_raw_email("ravi@example.com", "Hi", "Body text")
    decoded = base64.urlsafe_b64decode(raw).decode()
    assert "To: ravi@example.com" in decoded and "Body text" in decoded
    with pytest.raises(ValidationFailedError):
        build_raw_email("not-an-email", "x", "y")
    html = base64.urlsafe_b64encode(b"<p>Hello <b>there</b></p>").decode().rstrip("=")
    assert (
        extract_body(
            {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/html", "body": {"data": html}}]}
        )
        == "Hello there"
    )


async def test_gmail_oauth_flow_stores_encrypted_tokens(client, alice, services, mock_http):
    res = await client.post("/api/v1/integrations/gmail/connect", headers=alice)
    url = urlparse(res.json()["authorization_url"])
    params = parse_qs(url.query)
    assert params["code_challenge_method"] == ["S256"] and params["access_type"] == ["offline"]
    assert "gmail.readonly" in params["scope"][0] and "gmail.compose" in params["scope"][0]
    state = params["state"][0]

    def token_endpoint(request):
        body = parse_qs(request.content.decode())
        assert body["code_verifier"][0] and body["code"] == ["auth-code"]
        return httpx.Response(
            200,
            json={
                "access_token": "ya29.access",
                "refresh_token": "1//refresh",
                "expires_in": 3600,
                "scope": "gmail.readonly gmail.compose",
            },
        )

    mock_http.overrides["https://oauth2.googleapis.com/token"] = token_endpoint
    mock_http.overrides["https://gmail.googleapis.com/gmail/v1/users/me/profile"] = lambda r: httpx.Response(
        200, json={"emailAddress": "alice@gmail.com"}
    )
    cb = await client.get(f"/api/v1/integrations/gmail/callback?state={state}&code=auth-code")
    assert cb.status_code in (302, 307) and cb.headers["location"].endswith("status=connected")

    async with session_scope(services.sessionmaker) as s:
        integ = (await s.execute(select(m.Integration))).scalar_one()
        assert integ.account_label == "alice@gmail.com"
        assert b"refresh" not in integ.credentials_ciphertext

    # State is single-use.
    replay = await client.get(f"/api/v1/integrations/gmail/callback?state={state}&code=auth-code")
    assert "oauth_state_invalid" in replay.headers["location"]

    listing = {i["provider"]: i for i in (await client.get("/api/v1/integrations", headers=alice)).json()}
    assert listing["gmail"]["status"] == "connected" and listing["youtube"]["status"] == "ready"

    # Gmail API calls use the decrypted token.
    def gmail_api(request):
        assert request.headers["authorization"] == "Bearer ya29.access"
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "msg123456"}]})
        return httpx.Response(
            200,
            json={
                "id": "msg123456",
                "labelIds": ["UNREAD"],
                "snippet": "Invoice",
                "payload": {
                    "headers": [{"name": "Subject", "value": "Invoice due"}, {"name": "From", "value": "billing@x.com"}]
                },
            },
        )

    mock_http.overrides["https://gmail.googleapis.com/gmail/v1/users/me/messages"] = gmail_api
    emails = (await client.get("/api/v1/gmail/messages?unread=true", headers=alice)).json()
    assert emails[0]["subject"] == "Invoice due" and emails[0]["unread"] is True


async def test_gmail_invalid_grant_marks_reconnect(client, alice, services, mock_http):
    uid = user_id("alice@example.com")
    await client.get("/api/v1/me", headers=alice)
    async with session_scope(services.sessionmaker) as s:
        integ = await services.credentials.save(
            s, uid, "gmail", {"access_token": "old", "refresh_token": "bad"}, expires_at=None
        )
        integ_id = integ.id
    mock_http.overrides["https://oauth2.googleapis.com/token"] = lambda r: httpx.Response(
        400, json={"error": "invalid_grant"}
    )
    res = await client.get("/api/v1/gmail/messages", headers=alice)
    assert res.status_code == 502 and res.json()["error"]["code"] == "oauth_invalid_grant"
    async with session_scope(services.sessionmaker) as s:
        assert (await s.get(m.Integration, integ_id)).status == "error"


async def test_gmail_not_configured_on_server(client, alice, services):
    services.settings.google_client_id = None
    res = await client.post("/api/v1/integrations/gmail/connect", headers=alice)
    assert res.status_code == 503 and res.json()["error"]["code"] == "gmail_not_configured"
    services.settings.google_client_id = "google-client-id"


def test_whatsapp_helpers():
    assert normalize_phone("+91 98765-43210") == "919876543210"
    with pytest.raises(ValidationFailedError):
        normalize_phone("12345")
    body = b'{"entry": []}'
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature("secret", body, sig)
    assert not verify_webhook_signature("secret", body + b" ", sig)
    assert not verify_webhook_signature("secret", body, None)


async def test_whatsapp_error_24h_window(client, alice, mock_http):
    await client.put(
        "/api/v1/integrations/whatsapp",
        json={"phone_number_id": "1234567890", "access_token": "EAAG" + "x" * 30},
        headers=alice,
    )
    mock_http.overrides["https://graph.facebook.com/"] = lambda r: httpx.Response(
        400, json={"error": {"code": 131047, "message": "Re-engagement message"}}
    )
    res = await client.post("/api/v1/whatsapp/messages", json={"to": "+919876543210", "message": "hi"}, headers=alice)
    assert res.status_code == 502 and "template is required" in res.json()["error"]["message"]


async def test_whatsapp_webhook(client, alice, services, settings):
    await client.put(
        "/api/v1/integrations/whatsapp",
        json={"phone_number_id": "1234567890", "access_token": "EAAG" + "x" * 30},
        headers=alice,
    )
    verify = await client.get(
        "/api/v1/integrations/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wa-verify&hub.challenge=42"
    )
    assert verify.text == "42"
    payload = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "1234567890"},
                                "messages": [
                                    {"from": "919876543210", "type": "text", "text": {"body": "Hello Nexora"}}
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()
    bad = await client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=payload,
        headers={"X-Hub-Signature-256": "sha256=00", "content-type": "application/json"},
    )
    assert bad.status_code == 403
    sig = "sha256=" + hmac.new(b"wa-app-secret", payload, hashlib.sha256).hexdigest()
    ok = await client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=payload,
        headers={"X-Hub-Signature-256": sig, "content-type": "application/json"},
    )
    assert ok.status_code == 200
    notes = (await client.get("/api/v1/notifications", headers=alice)).json()["items"]
    assert notes[0]["body"] == "Hello Nexora"


async def test_disconnect_wipes_credentials(client, alice, services):
    await client.put(
        "/api/v1/integrations/whatsapp",
        json={"phone_number_id": "1234567890", "access_token": "EAAG" + "x" * 30},
        headers=alice,
    )
    assert (await client.post("/api/v1/integrations/whatsapp/disconnect", headers=alice)).status_code == 200
    async with session_scope(services.sessionmaker) as s:
        integ = (await s.execute(select(m.Integration))).scalar_one()
        assert integ.status == "disconnected" and integ.credentials_ciphertext is None


async def test_overpass_overload_falls_back_then_reports_busy(services, mock_http, monkeypatch):
    import asyncio as _asyncio

    from app.integrations.maps.osm import OSMPlacesProvider

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(_asyncio, "sleep", no_sleep)
    hits: list[str] = []

    def busy(request):
        hits.append(str(request.url))
        return httpx.Response(504, text="at capacity")

    mock_http.overrides["https://busy.example/"] = busy
    provider = OSMPlacesProvider(
        services.http,
        nominatim_url="https://nominatim.openstreetmap.org",
        overpass_url="https://busy.example/api, https://overpass-api.de/api/interpreter",
        user_agent="test",
    )
    places = await provider.nearby("petrol_pump", 13.0827, 80.2707)
    assert places and len(hits) == 1  # first endpoint busy, second served the request

    only_busy = OSMPlacesProvider(
        services.http,
        nominatim_url="https://nominatim.openstreetmap.org",
        overpass_url="https://busy.example/api",
        user_agent="test",
    )
    with pytest.raises(UpstreamError) as exc:
        await only_busy.nearby("atm", 13.0, 80.0)
    assert exc.value.code == "places_unavailable" and len(hits) == 3  # retried once
