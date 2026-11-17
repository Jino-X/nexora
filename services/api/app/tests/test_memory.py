"""Memory: retrieval, secret refusal, retention, privacy settings."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.exceptions import ValidationFailedError
from app.database import models as m
from app.database.base import utcnow
from app.database.session import session_scope
from app.memory.service import looks_like_secret
from app.tests.conftest import user_id

ALICE = user_id("alice@example.com")


async def _profile(services):
    from app.database import repositories as repo

    async with session_scope(services.sessionmaker) as s:
        await repo.ensure_profile(s, ALICE, "alice@example.com")


async def test_semantic_retrieval_ranks_relevant_memory(services):
    await _profile(services)
    async with session_scope(services.sessionmaker) as s:
        for text in [
            "Alice's upcoming project is a Tamil voice assistant called Nexora",
            "Alice prefers filter coffee in the morning",
            "Alice's sister lives in Coimbatore",
        ]:
            await services.memory.create(s, ALICE, text)
    async with session_scope(services.sessionmaker) as s:
        hits = await services.memory.search(s, ALICE, "upcoming project", limit=2)
    assert hits and "project" in hits[0][0].content


@pytest.mark.parametrize(
    "text",
    ["my password is hunter2", "key sk-abcdefghijklmnopqrstuvwxyz", "card 4111 1111 1111 1111", "AKIAABCDEFGHIJKLMNOP"],
)
def test_secret_detector(text):
    assert looks_like_secret(text)


def test_secret_detector_allows_normal_text():
    assert not looks_like_secret("I like long walks and my dog's name is Bruno")


async def test_memory_refuses_secrets(services):
    await _profile(services)
    async with session_scope(services.sessionmaker) as s:
        with pytest.raises(ValidationFailedError) as exc:
            await services.memory.create(s, ALICE, "my bank password is hunter2")
    assert exc.value.code == "secret_in_memory"


async def test_expired_memories_are_hidden(services):
    await _profile(services)
    async with session_scope(services.sessionmaker) as s:
        mem = await services.memory.create(s, ALICE, "Temporary note about the dentist")
        mem.expires_at = utcnow() - timedelta(minutes=1)
    async with session_scope(services.sessionmaker) as s:
        assert await services.memory.search(s, ALICE, "dentist") == []
        rows, _ = await services.memory.list(s, ALICE, kind=None, limit=10, offset=0)
        assert rows == []


async def test_memory_api_crud_export(client, alice):
    created = (
        await client.post(
            "/api/v1/memories", json={"content": "Prefers Tamil replies", "kind": "preference"}, headers=alice
        )
    ).json()
    assert created["embedding_model"] == "hashing-v1"
    updated = (await client.patch(f"/api/v1/memories/{created['id']}", json={"pinned": True}, headers=alice)).json()
    assert updated["pinned"] is True
    exported = (await client.get("/api/v1/memories/export", headers=alice)).json()
    assert len(exported["memories"]) == 1 and "embedding" not in exported["memories"][0]
    assert (await client.delete("/api/v1/memories", headers=alice)).status_code == 422  # needs confirm
    assert (await client.delete("/api/v1/memories?confirm=true", headers=alice)).status_code == 200
    assert (await client.get("/api/v1/memories", headers=alice)).json()["items"] == []


async def test_memory_disabled_blocks_tools(client, alice, services):
    from app.tests.conftest import call, say, use_llm

    await client.patch("/api/v1/me/preferences", json={"memory_enabled": False}, headers=alice)
    use_llm(services, call("memory_save", content="Alice likes jazz"), say("ok"))
    await client.post("/api/v1/assistant/runs", json={"message": "remember I like jazz"}, headers=alice)
    async with session_scope(services.sessionmaker) as s:
        from sqlalchemy import select

        assert (await s.execute(select(m.Memory))).scalars().all() == []
