"""Voice sessions: LiveKit token scoping, internal turn authorization, lifecycle."""

from __future__ import annotations

import json

import httpx
import jwt

from app.tests.conftest import INTERNAL_KEY, make_settings, parse_sse, user_id


async def _session(client, headers, **body):
    res = await client.post("/api/v1/voice/sessions", json={"activation": "push_to_talk", **body}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def test_token_is_scoped_to_private_room(client, alice, settings):
    vs = await _session(client, alice, activation="wake_word")
    claims = jwt.decode(
        vs["participant_token"],
        settings.livekit_api_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert claims["sub"] == str(user_id("alice@example.com"))
    assert claims["video"]["room"] == vs["room_name"] and claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublishSources"] == ["microphone"]
    assert claims["exp"] - claims["nbf"] <= settings.voice_token_ttl_seconds + 5
    dispatch = claims["roomConfig"]["agents"][0]
    assert dispatch["agentName"] == settings.livekit_agent_name
    assert json.loads(dispatch["metadata"])["voice_session_id"] == vs["session_id"]


async def test_new_session_supersedes_old(client, alice):
    first = await _session(client, alice)
    await _session(client, alice)
    sessions = (await client.get("/api/v1/voice/sessions", headers=alice)).json()["items"]
    old = next(s for s in sessions if s["id"] == first["session_id"])
    assert old["status"] == "ended" and old["end_reason"] == "superseded"


def _turn(vs, **over):
    return {
        "session_id": vs["session_id"],
        "room_name": vs["room_name"],
        "participant_identity": vs["participant_identity"],
        "text": "weather in Chennai",
        **over,
    }


async def test_internal_turn_requires_service_key(client, alice):
    vs = await _session(client, alice)
    res = await client.post("/api/v1/internal/voice/turns", json=_turn(vs))
    assert res.status_code == 401
    res = await client.post("/api/v1/internal/voice/turns", json=_turn(vs), headers={"X-Nexora-Internal-Key": "wrong"})
    assert res.status_code == 401


async def test_internal_turn_verifies_room_and_identity(client, alice, bob):
    vs = await _session(client, alice)
    hdr = {"X-Nexora-Internal-Key": INTERNAL_KEY}
    bob_id = str(user_id("bob@example.com"))
    assert (
        await client.post("/api/v1/internal/voice/turns", json=_turn(vs, participant_identity=bob_id), headers=hdr)
    ).status_code == 403
    assert (
        await client.post("/api/v1/internal/voice/turns", json=_turn(vs, room_name="nxr-other"), headers=hdr)
    ).status_code == 403


async def test_voice_turn_runs_shared_graph(client, alice):
    vs = await _session(client, alice)
    res = await client.post(
        "/api/v1/internal/voice/turns", json=_turn(vs), headers={"X-Nexora-Internal-Key": INTERNAL_KEY}
    )
    assert res.status_code == 200
    events = parse_sse(res.text)
    end = next(d for t, d in events if t == "message_end")
    assert end["conversation_id"] == vs["conversation_id"] and "°C" in end["content"]
    conv = (await client.get(f"/api/v1/conversations/{vs['conversation_id']}", headers=alice)).json()
    assert [msg["channel"] for msg in conv["messages"]] == ["voice", "voice"]


async def test_ended_session_rejects_turns(client, alice):
    vs = await _session(client, alice)
    assert (await client.post(f"/api/v1/voice/sessions/{vs['session_id']}/end", headers=alice)).status_code == 200
    res = await client.post(
        "/api/v1/internal/voice/turns", json=_turn(vs), headers={"X-Nexora-Internal-Key": INTERNAL_KEY}
    )
    assert res.status_code == 409


async def test_metrics_event_recorded(client, alice):
    vs = await _session(client, alice)
    res = await client.post(
        "/api/v1/internal/voice/events",
        headers={"X-Nexora-Internal-Key": INTERNAL_KEY},
        json={
            "session_id": vs["session_id"],
            "room_name": vs["room_name"],
            "event": "metrics",
            "metrics": {"stt_ms": 320.0, "llm_ttft_ms": 450.0, "end_to_end_ms": 1300.0},
        },
    )
    assert res.status_code == 200
    usage = (await client.get("/api/v1/me/usage", headers=alice)).json()["rows"]
    assert any(r["event_type"] == "voice_metrics" for r in usage)


async def test_voice_not_configured(tmp_path, mock_http):
    from app.main import create_app
    from app.services import build_services, close_services
    from app.tests.conftest import auth_headers

    s = make_settings(tmp_path, livekit_url=None, livekit_api_key=None, livekit_api_secret=None)
    svc = await build_services(s, http=httpx.AsyncClient(transport=httpx.MockTransport(mock_http.handler)))
    app = create_app(s, svc)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            res = await c.post("/api/v1/voice/sessions", json={}, headers=auth_headers(s))
            assert res.status_code == 503 and res.json()["error"]["code"] == "voice_not_configured"
            status = (await c.get("/api/v1/system/status")).json()
            assert status["voice"]["livekit"] is False
    await close_services(svc)
