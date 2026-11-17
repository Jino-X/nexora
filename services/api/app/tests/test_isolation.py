"""User isolation: one user can never read or modify another user's resources."""

from __future__ import annotations

import pytest


async def _seed(client, headers):
    conv = (await client.post("/api/v1/conversations", json={"title": "Secret project"}, headers=headers)).json()
    mem = (await client.post("/api/v1/memories", json={"content": "Alice's project is Apollo"}, headers=headers)).json()
    item = (
        await client.post(
            "/api/v1/vault", json={"name": "openai", "kind": "api_key", "secret": "very-secret-value"}, headers=headers
        )
    ).json()
    rule = (
        await client.post(
            "/api/v1/automations",
            json={
                "kind": "reminder",
                "name": "Pay rent",
                "schedule": {"type": "daily", "time": "09:00"},
                "timezone": "Asia/Kolkata",
                "config": {"message": "Pay rent"},
            },
            headers=headers,
        )
    ).json()
    return conv, mem, item, rule


async def test_cross_user_access_is_not_found(client, alice, bob):
    conv, mem, item, rule = await _seed(client, alice)

    for method, path, body in [
        ("GET", f"/api/v1/conversations/{conv['id']}", None),
        ("PATCH", f"/api/v1/conversations/{conv['id']}", {"title": "pwned"}),
        ("DELETE", f"/api/v1/conversations/{conv['id']}", None),
        ("PATCH", f"/api/v1/memories/{mem['id']}", {"content": "pwned"}),
        ("DELETE", f"/api/v1/memories/{mem['id']}", None),
        ("POST", f"/api/v1/vault/{item['id']}/reveal", None),
        ("PATCH", f"/api/v1/vault/{item['id']}", {"name": "pwned"}),
        ("DELETE", f"/api/v1/vault/{item['id']}", None),
        ("GET", f"/api/v1/automations/{rule['id']}", None),
        ("PATCH", f"/api/v1/automations/{rule['id']}", {"enabled": False}),
        ("POST", f"/api/v1/automations/{rule['id']}/run", None),
        ("DELETE", f"/api/v1/automations/{rule['id']}", None),
    ]:
        res = await client.request(method, path, json=body, headers=bob)
        assert res.status_code == 404, (method, path, res.status_code)

    # Bob's listings never contain Alice's data.
    assert (await client.get("/api/v1/conversations", headers=bob)).json()["items"] == []
    assert (await client.get("/api/v1/memories", headers=bob)).json()["items"] == []
    assert (await client.get("/api/v1/memories?q=Apollo", headers=bob)).json()["items"] == []
    assert (await client.get("/api/v1/vault", headers=bob)).json() == []
    assert (await client.get("/api/v1/automations", headers=bob)).json() == []

    # Alice's data is intact.
    assert (await client.get(f"/api/v1/conversations/{conv['id']}", headers=alice)).json()["conversation"][
        "title"
    ] == "Secret project"
    reveal = await client.post(f"/api/v1/vault/{item['id']}/reveal", headers=alice)
    assert reveal.json()["secret"] == "very-secret-value"


async def test_cannot_post_into_foreign_conversation(client, alice, bob):
    conv = (await client.post("/api/v1/conversations", json={}, headers=alice)).json()
    res = await client.post(
        "/api/v1/assistant/runs", json={"message": "hi", "conversation_id": conv["id"]}, headers=bob
    )
    assert res.status_code == 404


async def test_cannot_resume_foreign_run(client, alice, bob):
    res = await client.post("/api/v1/assistant/runs", json={"message": "hello"}, headers=alice)
    run_id = res.text.split('"run_id": "')[1].split('"')[0]
    assert (await client.get(f"/api/v1/assistant/runs/{run_id}", headers=alice)).status_code == 200
    assert (await client.get(f"/api/v1/assistant/runs/{run_id}", headers=bob)).status_code == 404
    assert (await client.post(f"/api/v1/assistant/runs/{run_id}/cancel", headers=bob)).status_code == 404


@pytest.mark.parametrize(
    "path",
    ["/api/v1/tasks", "/api/v1/approvals", "/api/v1/notifications", "/api/v1/voice/sessions", "/api/v1/vault/audit"],
)
async def test_lists_are_scoped(client, alice, bob, path):
    await _seed(client, alice)
    assert (await client.get(path, headers=bob)).json()["items"] == []
