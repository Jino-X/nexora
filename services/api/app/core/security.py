"""Authentication: Supabase JWT verification (JWKS for asymmetric keys, HS256 for the legacy secret),
a development-only token issuer, and the internal service key used by the voice agent."""

from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import PyJWKClient

from app.config import Settings
from app.core.exceptions import AuthenticationError

DEV_ISSUER = "nexora-dev"


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    claims: dict[str, Any] = field(repr=False)

    def last_sign_in_age_seconds(self) -> float | None:
        """Seconds since the most recent authentication method in the Supabase `amr` claim."""
        amr = self.claims.get("amr")
        stamps = [int(item.get("timestamp", 0)) for item in amr or [] if isinstance(item, dict)]
        if not stamps:
            iat = self.claims.get("iat")
            return time.time() - float(iat) if self.claims.get("iss") == DEV_ISSUER and iat else None
        return time.time() - max(stamps)


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks: PyJWKClient | None = None
        if settings.supabase_url:
            self._jwks = PyJWKClient(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
                cache_keys=True,
                lifespan=600,
                timeout=5,
            )
        self._supabase_issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Malformed access token") from exc

        alg = header.get("alg")
        issuer = unverified.get("iss")
        key: Any
        expected_issuer: str | None

        if alg == "HS256" and issuer == DEV_ISSUER:
            if not (self.settings.auth_dev_mode and self.settings.dev_jwt_secret):
                raise AuthenticationError("Development tokens are disabled")
            key, expected_issuer = self.settings.dev_jwt_secret.get_secret_value(), DEV_ISSUER
        elif alg == "HS256":
            if not self.settings.supabase_jwt_secret:
                raise AuthenticationError("HS256 tokens are not accepted by this server")
            key, expected_issuer = self.settings.supabase_jwt_secret.get_secret_value(), self._supabase_issuer
        elif alg in ("ES256", "RS256", "EdDSA") and self._jwks is not None:
            try:
                signing_key = await asyncio.to_thread(self._jwks.get_signing_key_from_jwt, token)
            except jwt.PyJWTError as exc:
                raise AuthenticationError("Unknown signing key") from exc
            key, expected_issuer = signing_key.key, self._supabase_issuer
        else:
            raise AuthenticationError("Unsupported token algorithm")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=self.settings.supabase_jwt_audience,
                issuer=expected_issuer,
                options={"require": ["exp", "sub", "aud"]},
                leeway=10,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Access token expired", code="token_expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid access token") from exc

        if claims.get("role") not in (None, "authenticated"):
            raise AuthenticationError("Token role is not allowed")
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:
            raise AuthenticationError("Invalid subject") from exc
        return AuthenticatedUser(id=user_id, email=claims.get("email"), claims=claims)


def issue_dev_token(settings: Settings, user_id: uuid.UUID, email: str) -> tuple[str, int]:
    """Mint a Supabase-shaped HS256 token for local development only."""
    if settings.app_env == "production" or not settings.auth_dev_mode or not settings.dev_jwt_secret:
        raise AuthenticationError("Development login is disabled")
    now = int(time.time())
    exp = now + settings.dev_token_ttl_seconds
    claims = {
        "sub": str(user_id),
        "email": email,
        "aud": settings.supabase_jwt_audience,
        "role": "authenticated",
        "iss": DEV_ISSUER,
        "iat": now,
        "exp": exp,
        "amr": [{"method": "dev", "timestamp": now}],
    }
    token = jwt.encode(claims, settings.dev_jwt_secret.get_secret_value(), algorithm="HS256")
    return token, exp


def dev_user_id(email: str) -> uuid.UUID:
    """Stable user id for a development email address."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"nexora-dev:{email.strip().lower()}")


def verify_internal_key(settings: Settings, provided: str | None) -> None:
    expected = settings.internal_service_key.get_secret_value() if settings.internal_service_key else None
    if not expected:
        raise AuthenticationError("Internal service authentication is not configured")
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        raise AuthenticationError("Invalid internal service key")
