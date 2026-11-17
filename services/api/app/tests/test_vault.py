"""Vault: envelope encryption properties, key rotation, API behaviour, audit trail."""

from __future__ import annotations

import base64
import uuid

import pytest
from sqlalchemy import select

from app.database import models as m
from app.database.session import session_scope
from app.tests.conftest import KEY_1, KEY_2, make_settings
from app.vault.encryption import DecryptionError, EnvelopeCipher, LocalKeyring, SealedBox


def cipher(keys: str, active: str) -> EnvelopeCipher:
    return EnvelopeCipher(LocalKeyring.from_config(keys, active))


def test_roundtrip_and_context_binding():
    c = cipher(f"k1:{KEY_1}", "k1")
    ctx = c.context("vault_item", "user-a", "item-1")
    box = c.seal(b"top secret", ctx)
    assert b"top secret" not in box.ciphertext and b"top secret" not in box.wrapped_key
    assert c.open(box, ctx) == b"top secret"
    for other in (
        c.context("vault_item", "user-b", "item-1"),
        c.context("vault_item", "user-a", "item-2"),
        c.context("integration_credentials", "user-a", "item-1"),
    ):
        with pytest.raises(DecryptionError):
            c.open(box, other)


def test_tampering_detected():
    c = cipher(f"k1:{KEY_1}", "k1")
    ctx = c.context("vault_item", "u", "i")
    box = c.seal(b"payload", ctx)
    flipped = bytearray(box.ciphertext)
    flipped[-1] ^= 0x01
    with pytest.raises(DecryptionError):
        c.open(SealedBox(box.key_id, box.wrapped_key, bytes(flipped)), ctx)


def test_unique_nonces_and_keys():
    c = cipher(f"k1:{KEY_1}", "k1")
    ctx = c.context("vault_item", "u", "i")
    a, b = c.seal(b"same", ctx), c.seal(b"same", ctx)
    assert a.ciphertext != b.ciphertext and a.wrapped_key != b.wrapped_key


def test_rotation_rewraps_without_touching_payload():
    old = cipher(f"k1:{KEY_1}", "k1")
    ctx = old.context("vault_item", "u", "i")
    box = old.seal(b"rotate me", ctx)
    rotated = cipher(f"k2:{KEY_2},k1:{KEY_1}", "k2")
    assert rotated.needs_rewrap(box)
    new_box = rotated.rewrap(box, ctx)
    assert new_box.key_id == "local:k2" and new_box.ciphertext == box.ciphertext
    assert rotated.open(new_box, ctx) == b"rotate me"
    with pytest.raises(DecryptionError):  # once k1 is retired, the old box is unreadable
        cipher(f"k2:{KEY_2}", "k2").open(box, ctx)


def test_keyring_validation():
    with pytest.raises(ValueError):
        LocalKeyring.from_config(f"k1:{base64.b64encode(b'short').decode()}", "k1")
    with pytest.raises(ValueError):
        LocalKeyring.from_config(f"k1:{KEY_1}", "missing")


async def test_vault_api_never_lists_secrets_and_audits_reveals(client, alice, services):
    res = await client.post(
        "/api/v1/vault",
        json={"name": "GitHub token", "kind": "api_key", "description": "CI", "secret": "ghp_supersecret"},
        headers=alice,
    )
    assert res.status_code == 201
    item = res.json()
    assert "secret" not in item and "ciphertext" not in item
    listing = await client.get("/api/v1/vault", headers=alice)
    assert "ghp_supersecret" not in listing.text

    revealed = await client.post(f"/api/v1/vault/{item['id']}/reveal", headers=alice)
    assert revealed.json()["secret"] == "ghp_supersecret"
    audit = (await client.get("/api/v1/vault/audit", headers=alice)).json()["items"]
    actions = [a["action"] for a in audit]
    assert "vault.revealed" in actions and "vault.created" in actions

    async with session_scope(services.sessionmaker) as s:
        row = (await s.execute(select(m.VaultItem).where(m.VaultItem.id == uuid.UUID(item["id"])))).scalar_one()
        assert b"ghp_supersecret" not in row.ciphertext

    dup = await client.post(
        "/api/v1/vault", json={"name": "GitHub token", "kind": "api_key", "secret": "x"}, headers=alice
    )
    assert dup.status_code == 409


async def test_vault_update_and_document(client, alice):
    doc = base64.b64encode(b"%PDF-1.7 fake").decode()
    item = (
        await client.post(
            "/api/v1/vault",
            json={"name": "Passport", "kind": "document", "file_base64": doc, "content_type": "application/pdf"},
            headers=alice,
        )
    ).json()
    await client.patch(f"/api/v1/vault/{item['id']}", json={"fields": {"number": "X123"}}, headers=alice)
    revealed = (await client.post(f"/api/v1/vault/{item['id']}/reveal", headers=alice)).json()
    assert revealed["fields"] == {"number": "X123"}


async def test_vault_not_configured(tmp_path, mock_http):
    import httpx

    from app.main import create_app
    from app.services import build_services, close_services

    s = make_settings(tmp_path, vault_master_keys=None)
    svc = await build_services(s, http=httpx.AsyncClient(transport=httpx.MockTransport(mock_http.handler)))
    app = create_app(s, svc)
    from app.tests.conftest import auth_headers

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            res = await c.post(
                "/api/v1/vault", json={"name": "x", "kind": "secret", "secret": "y"}, headers=auth_headers(s)
            )
            assert res.status_code == 503 and res.json()["error"]["code"] == "vault_not_configured"
    await close_services(svc)


async def test_vault_reauth_requirement(client, alice, services):
    item = (
        await client.post("/api/v1/vault", json={"name": "pin", "kind": "secret", "secret": "1234"}, headers=alice)
    ).json()
    services.settings.vault_reauth_max_age_minutes = 1  # dev tokens carry amr with "now"
    assert (await client.post(f"/api/v1/vault/{item['id']}/reveal", headers=alice)).status_code == 200
    services.settings.vault_reauth_max_age_minutes = 0


async def test_rotation_script_rewraps_vault_and_credentials(tmp_path, mock_http, monkeypatch):
    import httpx

    from app.scripts import rotate_vault_keys
    from app.services import build_services, close_services
    from app.tests.conftest import user_id

    db = f"sqlite+aiosqlite:///{tmp_path}/rot.db"
    old = make_settings(tmp_path, database_url=db)
    svc = await build_services(old, http=httpx.AsyncClient(transport=httpx.MockTransport(mock_http.handler)))
    uid = user_id("alice@example.com")
    async with session_scope(svc.sessionmaker) as s:
        from app.database import repositories as repo

        await repo.ensure_profile(s, uid, "alice@example.com")
        item = await svc.vault.create(s, uid, name="k", kind="secret", description=None, secret="s3cr3t")
        await svc.credentials.save(s, uid, "whatsapp", {"access_token": "EAAtoken"})
        item_id = item.id
    await close_services(svc)

    new = make_settings(tmp_path, database_url=db, vault_master_keys=f"k2:{KEY_2},k1:{KEY_1}", vault_active_key_id="k2")
    monkeypatch.setattr(rotate_vault_keys, "get_settings", lambda: new)
    assert await rotate_vault_keys.rotate() == 0
    assert await rotate_vault_keys.rotate() == 0  # idempotent

    only_new = make_settings(tmp_path, database_url=db, vault_master_keys=f"k2:{KEY_2}", vault_active_key_id="k2")
    svc = await build_services(only_new, http=httpx.AsyncClient(transport=httpx.MockTransport(mock_http.handler)))
    async with session_scope(svc.sessionmaker) as s:
        assert (await svc.vault.reveal(s, uid, item_id))["secret"] == "s3cr3t"
        integ = (await s.execute(select(m.Integration))).scalar_one()
        assert svc.credentials.load(integ)["access_token"] == "EAAtoken"
    await close_services(svc)
