"""Assistant graph: tool orchestration, permissions, approvals, streaming, failure handling."""

from __future__ import annotations

import asyncio
import json

import httpx
from sqlalchemy import select

from app.database import models as m
from app.database.session import session_scope
from app.llm.base import LLMError
from app.tests.conftest import call, parse_sse, say, use_llm, user_id

ALICE = user_id("alice@example.com")


async def _run(client, headers, message, **extra):
    res = await client.post("/api/v1/assistant/runs", json={"message": message, **extra}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    return parse_sse(res.text)


def _types(events):
    return [e[0] for e in events]


async def test_offline_mode_weather_tool_end_to_end(client, alice):
    events = await _run(client, alice, "What's the weather in Chennai?")
    types = _types(events)
    assert types[0] == "run_started" and types[-1] == "done"
    assert "tool_start" in types and "message_end" in types
    tool_end = next(d for t, d in events if t == "tool_end")
    assert tool_end["tool"] == "weather_forecast" and tool_end["ok"] is True
    assert tool_end["card"]["type"] == "weather"
    end = next(d for t, d in events if t == "message_end")
    assert end["offline"] is True and "°C" in end["content"]
    conv = (await client.get(f"/api/v1/conversations/{end['conversation_id']}", headers=alice)).json()
    roles = [msg["role"] for msg in conv["messages"]]
    assert roles == ["user", "assistant"]
    assert conv["messages"][1]["meta"]["cards"][0]["type"] == "weather"
    assert conv["conversation"]["title"].startswith("What's the weather")


async def test_scripted_llm_multi_step_with_location(client, alice, services):
    llm = use_llm(services, call("places_nearby", category="petrol_pump"), say("The closest is Indian Oil."))
    events = await _run(client, alice, "Find a petrol pump near me", location={"latitude": 13.08, "longitude": 80.27})
    card = next(d for t, d in events if t == "tool_end")["card"]
    assert card["type"] == "places" and card["places"][0]["name"] == "Indian Oil"
    # Second LLM call received the tool result.
    second_messages = llm.requests[1][0]
    assert second_messages[-1].role == "tool" and "Indian Oil" in second_messages[-1].content
    end = next(d for t, d in events if t == "message_end")
    assert end["content"].strip() == "The closest is Indian Oil."


async def test_location_required_without_sharing(client, alice, services):
    use_llm(services, call("places_nearby", category="atm"), say("Please share your location."))
    events = await _run(client, alice, "nearest atm")
    tool_end = next(d for t, d in events if t == "tool_end")
    assert tool_end["ok"] is False and tool_end["error_code"] == "location_required"


async def test_invalid_tool_arguments_go_back_to_llm(client, alice, services):
    llm = use_llm(services, call("places_nearby", category="spaceport"), say("Sorry."))
    await _run(client, alice, "find a spaceport")
    tool_msg = llm.requests[1][0][-1]
    assert tool_msg.role == "tool" and "Invalid arguments" in tool_msg.content


async def test_unknown_tool_ignored(client, alice, services):
    use_llm(services, call("run_shell", cmd="rm -rf /"), say("I can't do that."))
    events = await _run(client, alice, "delete everything")
    assert "tool_start" not in _types(events)


async def test_sensitive_tool_creates_approval_and_executes_once(client, alice, services, mock_http):
    sent: list[dict] = []

    def graph_api(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    mock_http.overrides["https://graph.facebook.com/"] = graph_api
    await client.put(
        "/api/v1/integrations/whatsapp",
        json={"phone_number_id": "1234567890", "access_token": "EAAG" + "x" * 30},
        headers=alice,
    )
    use_llm(
        services,
        call("whatsapp_send_message", to="+919876543210", message="Running late"),
        say("I've prepared the message; approve it in the app."),
    )
    events = await _run(client, alice, "WhatsApp Ravi that I'm running late")
    approval = next(d for t, d in events if t == "approval_required")
    assert "Running late" in approval["summary"]
    assert sent == []  # nothing sent before approval

    res = await client.post(f"/api/v1/approvals/{approval['approval_id']}/approve", headers=alice)
    assert res.status_code == 200 and res.json()["status"] == "executed"
    assert len(sent) == 1 and sent[0]["to"] == "919876543210"
    again = await client.post(f"/api/v1/approvals/{approval['approval_id']}/approve", headers=alice)
    assert again.status_code == 409
    assert len(sent) == 1

    tasks = (await client.get("/api/v1/tasks?kind=approval", headers=alice)).json()["items"]
    assert tasks[0]["status"] == "succeeded"


async def test_concurrent_approvals_execute_once(client, alice, services, mock_http):
    sent: list[int] = []

    def graph_api(request: httpx.Request) -> httpx.Response:
        sent.append(1)
        return httpx.Response(200, json={"messages": [{"id": "wamid.2"}]})

    mock_http.overrides["https://graph.facebook.com/"] = graph_api
    await client.put(
        "/api/v1/integrations/whatsapp",
        json={"phone_number_id": "1234567890", "access_token": "EAAG" + "x" * 30},
        headers=alice,
    )
    use_llm(services, call("whatsapp_send_message", to="+919876543210", message="hi"), say("ok"))
    events = await _run(client, alice, "say hi to ravi")
    aid = next(d for t, d in events if t == "approval_required")["approval_id"]
    results = await asyncio.gather(*[client.post(f"/api/v1/approvals/{aid}/approve", headers=alice) for _ in range(4)])
    assert sorted(r.status_code for r in results).count(200) == 1
    assert len(sent) == 1


async def test_reject_approval(client, alice, services):
    await client.put(
        "/api/v1/integrations/whatsapp",
        json={"phone_number_id": "1234567890", "access_token": "EAAG" + "x" * 30},
        headers=alice,
    )
    use_llm(services, call("whatsapp_send_message", to="+919876543210", message="hi"), say("ok"))
    events = await _run(client, alice, "say hi")
    aid = next(d for t, d in events if t == "approval_required")["approval_id"]
    res = await client.post(f"/api/v1/approvals/{aid}/reject", headers=alice)
    assert res.json()["status"] == "rejected"
    assert (await client.post(f"/api/v1/approvals/{aid}/approve", headers=alice)).status_code == 409


async def test_integration_not_connected_is_denied(client, alice, services):
    use_llm(services, call("gmail_unread"), say("Connect Gmail first."))
    events = await _run(client, alice, "summarize my unread emails")
    tool_end = next(d for t, d in events if t == "tool_end")
    assert tool_end["ok"] is False and tool_end["error_code"] == "gmail_not_connected"


async def test_disabled_tool_permission(client, alice, services):
    await client.put("/api/v1/permissions/tools/weather_forecast", json={"enabled": False}, headers=alice)
    llm = use_llm(services, say("Weather is disabled."))
    await _run(client, alice, "weather?")
    offered = {t["function"]["name"] for t in llm.requests[0][1] or []}
    assert "weather_forecast" not in offered
    perms = (await client.get("/api/v1/permissions/tools", headers=alice)).json()
    assert next(p for p in perms if p["tool_name"] == "weather_forecast")["enabled"] is False
    assert next(p for p in perms if p["tool_name"] == "gmail_send_email")["requires_approval"] is True


async def test_llm_failure_is_reported_and_persisted(client, alice, services):
    use_llm(services, LLMError("boom"))
    events = await _run(client, alice, "hello")
    err = next(d for t, d in events if t == "error")
    assert err["code"] == "llm_error" and err["retryable"] is True
    async with session_scope(services.sessionmaker) as s:
        msgs = (await s.execute(select(m.Message).where(m.Message.role == "assistant"))).scalars().all()
        assert msgs[-1].status == "error"


async def test_retry_regenerates_last_user_message(client, alice, services):
    events = await _run(client, alice, "news about ai")
    conv_id = next(d for t, d in events if t == "run_started")["conversation_id"]
    llm = use_llm(services, say("Here is a fresh answer."))
    events = await _run(client, alice, "", conversation_id=conv_id, regenerate=True)
    assert "message_end" in _types(events)
    last_user = [msg for msg in llm.requests[0][0] if msg.role == "user"][-1]
    assert last_user.content == "news about ai"
    conv = (await client.get(f"/api/v1/conversations/{conv_id}", headers=alice)).json()
    assert [msg["role"] for msg in conv["messages"]].count("user") == 1


async def test_history_is_included_and_memory_injected(client, alice, services):
    await client.post("/api/v1/memories", json={"content": "Alice's upcoming project is Apollo launch"}, headers=alice)
    first = await _run(client, alice, "hello there")
    conv_id = next(d for t, d in first if t == "run_started")["conversation_id"]
    llm = use_llm(services, say("Apollo launch, right?"))
    await _run(client, alice, "What did I tell you about my upcoming project?", conversation_id=conv_id)
    messages = llm.requests[0][0]
    assert "Apollo" in messages[0].content  # memory in system prompt
    assert any(msg.role == "user" and msg.content == "hello there" for msg in messages)


async def test_voice_channel_prompt_is_spoken_style(services):
    from app.assistant.prompts import build_system_prompt

    prompt = build_system_prompt(
        name="A",
        now_local=__import__("datetime").datetime.now(),
        timezone="UTC",
        location_label=None,
        has_location=False,
        language="ta",
        style="concise",
        channel="voice",
        memories=[],
    )
    assert "spoken aloud" in prompt and "Tamil" in prompt


async def test_cancel_run(client, alice, services):
    class SlowLLM(type(use_llm(services))):  # type: ignore[misc]
        async def chat(self, messages, **kw):
            await kw["on_token"]("partial ")
            await asyncio.sleep(10)

    from app.tests.conftest import FakeRouter

    services.llm = FakeRouter(SlowLLM([]))  # type: ignore[assignment]
    from app.assistant.service import TurnRequest, execute_turn, prepare_turn

    req = TurnRequest(user_id=ALICE, text="tell me a long story")
    await client.get("/api/v1/me", headers=alice)
    prepared = await prepare_turn(services, req)
    run = services.runs.start(
        user_id=ALICE,
        conversation_id=prepared.conversation_id,
        channel="text",
        body=lambda r: execute_turn(services, req, prepared, r),
    )
    await asyncio.sleep(0.2)
    res = await client.post(f"/api/v1/assistant/runs/{run.id}/cancel", headers=alice)
    assert res.json()["status"] == "cancelled"
    async with session_scope(services.sessionmaker) as s:
        msg = (await s.execute(select(m.Message).where(m.Message.role == "assistant"))).scalars().one()
        assert msg.status == "cancelled" and msg.content == "partial"

    # Resume replays every event from a given sequence number.
    replay = await client.get(f"/api/v1/assistant/runs/{run.id}/events?after=1", headers=alice)
    names = [e[0] for e in parse_sse(replay.text)]
    assert "run_started" not in names and "cancelled" in names
