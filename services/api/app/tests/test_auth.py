"""Authentication: Supabase JWT verification paths, dev tokens, internal service key."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.exceptions import AuthenticationError
from app.core.security import TokenVerifier, issue_dev_token, verify_internal_key
from app.tests.conftest import INTERNAL_KEY, make_settings


def _claims(**extra: object) -> dict[str, object]:
    now = int(time.time())
    return {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 600,
        **extra,
    }


async def test_dev_token_roundtrip(settings):
    uid = uuid.uuid4()
    token, _ = issue_dev_token(settings, uid, "a@example.com")
    user = await TokenVerifier(settings).verify(token)
    assert user.id == uid and user.email == "a@example.com"


async def test_dev_token_rejected_when_dev_mode_off(settings, tmp_path):
    token, _ = issue_dev_token(settings, uuid.uuid4(), "a@example.com")
    strict = make_settings(
        tmp_path, auth_dev_mode=False, dev_jwt_secret=None, supabase_jwt_secret="supabase-secret-0123456789abcdef"
    )
    with pytest.raises(AuthenticationError):
        await TokenVerifier(strict).verify(token)


async def test_supabase_hs256_secret(tmp_path):
    s = make_settings(
        tmp_path, supabase_url="https://proj.supabase.co", supabase_jwt_secret="supabase-secret-0123456789abcdef"
    )
    good = jwt.encode(_claims(iss="https://proj.supabase.co/auth/v1"), "supabase-secret-0123456789abcdef", "HS256")
    assert (await TokenVerifier(s).verify(good)).id
    wrong_iss = jwt.encode(_claims(iss="https://evil.example/auth/v1"), "supabase-secret-0123456789abcdef", "HS256")
    with pytest.raises(AuthenticationError):
        await TokenVerifier(s).verify(wrong_iss)
    forged = jwt.encode(_claims(iss="https://proj.supabase.co/auth/v1"), "wrong-secret-0123456789abcdefgh", "HS256")
    with pytest.raises(AuthenticationError):
        await TokenVerifier(s).verify(forged)


async def test_supabase_es256_jwks(tmp_path, monkeypatch):
    s = make_settings(tmp_path, supabase_url="https://proj.supabase.co")
    key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_claims(iss="https://proj.supabase.co/auth/v1"), key, "ES256", headers={"kid": "k1"})
    verifier = TokenVerifier(s)

    class FakeKey:
        def __init__(self, k):
            self.key = k

    monkeypatch.setattr(verifier._jwks, "get_signing_key_from_jwt", lambda t: FakeKey(key.public_key()))
    assert (await verifier.verify(token)).id
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(verifier._jwks, "get_signing_key_from_jwt", lambda t: FakeKey(other.public_key()))
    with pytest.raises(AuthenticationError):
        await verifier.verify(token)


async def test_expired_and_wrong_audience(settings):
    secret = settings.dev_jwt_secret.get_secret_value()
    expired = jwt.encode(_claims(iss="nexora-dev", exp=int(time.time()) - 100), secret, "HS256")
    with pytest.raises(AuthenticationError) as exc:
        await TokenVerifier(settings).verify(expired)
    assert exc.value.code == "token_expired"
    wrong_aud = jwt.encode(_claims(iss="nexora-dev", aud="anon"), secret, "HS256")
    with pytest.raises(AuthenticationError):
        await TokenVerifier(settings).verify(wrong_aud)
    service_role = jwt.encode(_claims(iss="nexora-dev", role="service_role"), secret, "HS256")
    with pytest.raises(AuthenticationError):
        await TokenVerifier(settings).verify(service_role)


async def test_alg_none_rejected(settings):
    token = jwt.encode(_claims(iss="nexora-dev"), None, "none")
    with pytest.raises(AuthenticationError):
        await TokenVerifier(settings).verify(token)


def test_internal_key(settings):
    verify_internal_key(settings, INTERNAL_KEY)
    with pytest.raises(AuthenticationError):
        verify_internal_key(settings, "nope")
    with pytest.raises(AuthenticationError):
        verify_internal_key(settings, None)


def test_production_config_guards(tmp_path):
    with pytest.raises(ValueError, match="AUTH_DEV_MODE"):
        make_settings(
            tmp_path,
            app_env="production",
            database_url="postgresql+asyncpg://x/y",
            supabase_url="https://p.supabase.co",
        )


async def test_api_requires_bearer(client):
    res = await client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
    res = await client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert res.status_code == 401


async def test_dev_login_and_profile_bootstrap(client):
    res = await client.post("/api/v1/auth/dev/login", json={"email": "carol@example.com", "display_name": "Carol"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["profile"]["email"] == "carol@example.com"
    assert body["preferences"]["memory_enabled"] is True
    # Voice starts hands-free: tapping the orb opens the mic straight away ("Hold to talk" is opt-in).
    assert body["preferences"]["push_to_talk_enabled"] is False
