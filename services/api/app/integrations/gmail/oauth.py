"""Google OAuth 2.0 (authorization code + PKCE) for Gmail.

Least-privilege scopes: `gmail.readonly` to list, search and read, and `gmail.compose` to create
drafts and send drafts. Both are Google *restricted* scopes: a public production app needs Google's
OAuth verification and an annual security assessment. Until then, keep the OAuth app in "Testing"
mode with named test users."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.exceptions import NotConfiguredError, UpstreamError, ValidationFailedError
from app.database import models as m
from app.database.base import utcnow

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - public endpoint, not a secret
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


class InvalidGrantError(UpstreamError):
    code = "oauth_invalid_grant"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class GoogleOAuth:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.http = http

    def _require(self) -> tuple[str, str]:
        if not self.settings.google_configured:
            raise NotConfiguredError(
                "Gmail is not configured on this server (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)",
                code="gmail_not_configured",
            )
        assert self.settings.google_client_id and self.settings.google_client_secret
        return self.settings.google_client_id, self.settings.google_client_secret.get_secret_value()

    async def authorization_url(self, session: AsyncSession, user_id: uuid.UUID) -> str:
        client_id, _ = self._require()
        await session.execute(delete(m.OAuthState).where(m.OAuthState.expires_at < utcnow()))
        state = secrets.token_urlsafe(32)
        verifier, challenge = _pkce_pair()
        session.add(
            m.OAuthState(
                state=state,
                user_id=user_id,
                provider="gmail",
                code_verifier=verifier,
                expires_at=utcnow() + timedelta(minutes=10),
            )
        )
        await session.flush()
        params = {
            "client_id": client_id,
            "redirect_uri": self.settings.gmail_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def consume_state(self, session: AsyncSession, state: str) -> m.OAuthState:
        row = (await session.execute(select(m.OAuthState).where(m.OAuthState.state == state))).scalar_one_or_none()
        if row is None or row.provider != "gmail":
            raise ValidationFailedError("Unknown or already used OAuth state", code="oauth_state_invalid")
        await session.delete(row)
        await session.flush()
        if row.expires_at < utcnow():
            raise ValidationFailedError("OAuth state expired, please try again", code="oauth_state_expired")
        return row

    async def exchange_code(self, code: str, verifier: str) -> dict[str, Any]:
        client_id, client_secret = self._require()
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.gmail_redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        client_id, client_secret = self._require()
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        )

    async def revoke(self, token: str) -> None:
        try:
            await self.http.post(REVOKE_URL, data={"token": token}, timeout=10)
        except httpx.HTTPError:
            pass  # best effort; local credentials are deleted regardless

    async def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        try:
            res = await self.http.post(TOKEN_URL, data=data, timeout=15)
        except httpx.HTTPError as exc:
            raise UpstreamError("Google OAuth is unreachable") from exc
        body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        if res.status_code == 400 and body.get("error") == "invalid_grant":
            raise InvalidGrantError("Google access was revoked or expired. Please reconnect Gmail.")
        if res.status_code >= 400 or "access_token" not in body:
            raise UpstreamError(f"Google OAuth error: {body.get('error', res.status_code)}")
        return body
