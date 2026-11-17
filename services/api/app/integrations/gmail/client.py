"""Gmail REST API client and the per-user service that manages token refresh."""

from __future__ import annotations

import base64
import re
import uuid
from datetime import timedelta
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotConfiguredError, UpstreamError, ValidationFailedError
from app.database import repositories as repo
from app.database.base import utcnow
from app.integrations.base import fetch_json
from app.integrations.credentials import CredentialStore
from app.integrations.gmail.oauth import GoogleOAuth, InvalidGrantError
from app.integrations.news.rss import clean_text

API = "https://gmail.googleapis.com/gmail/v1/users/me"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailSummary(BaseModel):
    id: str
    thread_id: str | None = None
    from_: str | None = None
    to: str | None = None
    subject: str | None = None
    date: str | None = None
    snippet: str | None = None
    unread: bool = False
    labels: list[str] = []


class EmailDetail(EmailSummary):
    body_text: str | None = None


class DraftResult(BaseModel):
    draft_id: str
    message_id: str | None = None
    to: str
    subject: str


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers") or []}


def _decode(data: str | None) -> str:
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def extract_body(payload: dict[str, Any]) -> str:
    """Prefer text/plain; fall back to stripped text/html."""
    plain: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if mime == "text/plain" and data:
            plain.append(_decode(data))
        elif mime == "text/html" and data:
            html_parts.append(_decode(data))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    return clean_text("\n".join(html_parts), limit=20_000) or ""


def parse_message(raw: dict[str, Any], *, with_body: bool = False) -> EmailDetail:
    payload = raw.get("payload") or {}
    h = _headers(payload)
    labels = raw.get("labelIds") or []
    detail = EmailDetail(
        id=raw["id"],
        thread_id=raw.get("threadId"),
        from_=h.get("from"),
        to=h.get("to"),
        subject=h.get("subject"),
        date=h.get("date"),
        snippet=clean_text(raw.get("snippet"), 300),
        unread="UNREAD" in labels,
        labels=labels,
    )
    if with_body:
        detail.body_text = extract_body(payload)[:20_000]
    return detail


def build_raw_email(to: str, subject: str, body: str, cc: str | None = None) -> str:
    for addr in [to, *(cc.split(",") if cc else [])]:
        _, email = parseaddr(addr.strip())
        if not EMAIL_RE.match(email):
            raise ValidationFailedError(f"Invalid email address: {addr.strip()}")
    msg = EmailMessage()
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject.replace("\n", " ")[:250]
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class GmailClient:
    def __init__(self, http: httpx.AsyncClient, access_token: str, timeout: float = 15.0) -> None:
        self.http = http
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.timeout = timeout

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await fetch_json(
            self.http,
            "GET",
            f"{API}{path}",
            provider="Gmail",
            params=params,
            headers=self.headers,
            timeout=self.timeout,
        )

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        return await fetch_json(
            self.http, "POST", f"{API}{path}", provider="Gmail", json=body, headers=self.headers, timeout=self.timeout
        )

    async def profile_email(self) -> str | None:
        return (await self._get("/profile")).get("emailAddress")

    async def list_messages(self, query: str = "", max_results: int = 10) -> list[EmailSummary]:
        data = await self._get("/messages", {"q": query[:300], "maxResults": max(1, min(max_results, 25))})
        results: list[EmailSummary] = []
        for ref in data.get("messages") or []:
            raw = await self._get(
                f"/messages/{ref['id']}",
                {"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]},
            )
            results.append(EmailSummary(**parse_message(raw).model_dump(exclude={"body_text"})))
        return results

    async def get_message(self, message_id: str) -> EmailDetail:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", message_id):
            raise ValidationFailedError("Invalid message id")
        return parse_message(await self._get(f"/messages/{message_id}", {"format": "full"}), with_body=True)

    async def create_draft(self, to: str, subject: str, body: str, cc: str | None = None) -> DraftResult:
        raw = build_raw_email(to, subject, body, cc)
        data = await self._post("/drafts", {"message": {"raw": raw}})
        return DraftResult(
            draft_id=data["id"], message_id=(data.get("message") or {}).get("id"), to=to, subject=subject
        )

    async def send_draft(self, draft_id: str) -> dict[str, Any]:
        data = await self._post("/drafts/send", {"id": draft_id})
        return {"message_id": data.get("id"), "thread_id": data.get("threadId")}


class GmailService:
    """Loads a user's encrypted Gmail tokens, refreshes them when needed, returns a client."""

    def __init__(self, oauth: GoogleOAuth, store: CredentialStore, http: httpx.AsyncClient) -> None:
        self.oauth = oauth
        self.store = store
        self.http = http

    async def client_for(self, session: AsyncSession, user_id: uuid.UUID) -> GmailClient:
        integ = await repo.get_integration(session, user_id, "gmail")
        if integ is None or integ.status != "connected":
            raise NotConfiguredError("Gmail is not connected. Connect it in Integrations.", code="gmail_not_connected")
        creds = self.store.load(integ)
        expires = integ.token_expires_at
        if not creds.get("access_token") or expires is None or expires - utcnow() < timedelta(seconds=90):
            refresh_token = creds.get("refresh_token")
            if not refresh_token:
                await self.store.mark_error(session, integ, "Missing refresh token, reconnect Gmail")
                await session.commit()  # persist the state even though this request fails
                raise NotConfiguredError("Gmail needs to be reconnected", code="gmail_reauth_required")
            try:
                token = await self.oauth.refresh(refresh_token)
            except InvalidGrantError:
                await self.store.mark_error(session, integ, "Google access was revoked or expired")
                await session.commit()
                raise
            creds["access_token"] = token["access_token"]
            if token.get("refresh_token"):
                creds["refresh_token"] = token["refresh_token"]
            await self.store.update_tokens(
                session, integ, creds, utcnow() + timedelta(seconds=int(token.get("expires_in", 3600)))
            )
        return GmailClient(self.http, creds["access_token"])

    async def complete_connection(self, session: AsyncSession, user_id: uuid.UUID, token: dict[str, Any]) -> str:
        if not token.get("refresh_token"):
            raise UpstreamError(
                "Google did not return a refresh token; remove Nexora's access in your Google account and connect again"
            )
        client = GmailClient(self.http, token["access_token"])
        email = await client.profile_email()
        await self.store.save(
            session,
            user_id,
            "gmail",
            {"access_token": token["access_token"], "refresh_token": token["refresh_token"]},
            account_label=email,
            scopes=str(token.get("scope", "")).split(),
            expires_at=utcnow() + timedelta(seconds=int(token.get("expires_in", 3600))),
        )
        return email or ""
