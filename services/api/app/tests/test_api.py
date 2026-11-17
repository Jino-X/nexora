"""API hardening: validation envelope, size limits, rate limits, pagination, export, deletion, schema sync."""

from __future__ import annotations

import re
from pathlib import Path

from app.database import models as m
from app.database.base import Base
from app.database.session import session_scope
from app.tests.conftest import user_id

MIGRATIONS = Path(__file__).resolve().parents[4] / "supabase" / "migrations"


async def test_validation_error_envelope(client, alice):
    res = await client.post("/api/v1/memories", json={"content": ""}, headers=alice)
    body = res.json()
    assert res.status_code == 422 and body["error"]["code"] == "validation_failed"
    assert body["error"]["request_id"] and res.headers["x-request-id"] == body["error"]["request_id"]


async def test_body_size_limit(client, alice):
    res = await client.post(
        "/api/v1/memories", content=b"x" * 7_000_000, headers={**alice, "content-type": "application/json"}
    )
    assert res.status_code == 413


async def test_rate_limit(client, alice, services):
    services.settings.assistant_rate_limit_per_minute = 2
    codes = [
        (await client.post("/api/v1/assistant/runs", json={"message": "hi"}, headers=alice)).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


async def test_security_headers(client):
    res = await client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff" and res.headers["x-frame-options"] == "DENY"


async def test_pagination(client, alice):
    for i in range(5):
        await client.post("/api/v1/conversations", json={"title": f"c{i}"}, headers=alice)
    page = (await client.get("/api/v1/conversations?limit=2", headers=alice)).json()
    assert len(page["items"]) == 2 and page["has_more"] and page["next_offset"] == 2
    last = (await client.get("/api/v1/conversations?limit=2&offset=4", headers=alice)).json()
    assert len(last["items"]) == 1 and not last["has_more"]


async def test_onboarding_and_preferences(client, alice):
    res = await client.post(
        "/api/v1/me/onboarding",
        json={"display_name": "Alice", "timezone": "Asia/Kolkata", "preferred_language": "ta"},
        headers=alice,
    )
    assert res.json()["profile"]["onboarded_at"] and res.json()["preferences"]["preferred_language"] == "ta"
    bad = await client.post("/api/v1/me/onboarding", json={"display_name": "A", "timezone": "Mars/Base"}, headers=alice)
    assert bad.status_code == 422
    half = await client.patch("/api/v1/me/preferences", json={"home_latitude": 10.0}, headers=alice)
    assert half.status_code == 422


async def test_export_excludes_secrets(client, alice):
    await client.post("/api/v1/vault", json={"name": "k", "kind": "secret", "secret": "s3cr3t-value"}, headers=alice)
    await client.post("/api/v1/memories", json={"content": "likes tea"}, headers=alice)
    res = await client.get("/api/v1/me/export", headers=alice)
    assert res.status_code == 200
    text = res.text
    assert "s3cr3t-value" not in text and "ciphertext" not in text and "likes tea" in text


async def test_account_deletion(client, alice, services):
    await client.post("/api/v1/memories", json={"content": "likes tea"}, headers=alice)
    assert (await client.request("DELETE", "/api/v1/me", json={"confirm": "nope"}, headers=alice)).status_code == 422
    res = await client.request("DELETE", "/api/v1/me", json={"confirm": "DELETE"}, headers=alice)
    assert res.status_code == 200
    async with session_scope(services.sessionmaker) as s:
        assert await s.get(m.Profile, user_id("alice@example.com")) is None


async def test_system_status_reports_offline_llm(client):
    status = (await client.get("/api/v1/system/status")).json()
    assert status["llm"]["primary"] == "offline" and status["auth"]["mode"] == "dev"
    assert "secret" not in str(status).lower().replace("vault", "")


def _parse_migration() -> dict[str, set[str]]:
    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql")))
    tables: dict[str, set[str]] = {}
    for match in re.finditer(r"create table public\.(\w+) \((.*?)\n\);", sql, re.S):
        cols = set()
        for line in match.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith(("unique", "foreign", "primary", "check", "constraint", "--", "on ")):
                continue
            cols.add(line.split()[0])
        tables[match.group(1)] = cols
    return tables


def test_orm_matches_supabase_migration():
    migration = _parse_migration()
    for table in Base.metadata.sorted_tables:
        assert table.name in migration, f"{table.name} missing from migration"
        assert {c.name for c in table.columns} == migration[table.name], table.name


def test_rls_enabled_on_every_user_table():
    sql = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql")))
    for table in ["profiles", *m.USER_OWNED_TABLES]:
        assert (
            f"alter table public.{table:<17} enable row level security" in sql
            or f"alter table public.{table} enable row level security" in sql
        ), table
