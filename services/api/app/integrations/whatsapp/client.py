"""WhatsApp Business Platform (Cloud API) adapter.

Only the official Graph API is supported, with a business phone number and an access token that
the user (or their business) provisions in Meta Business Manager. Free-form text can only be sent
inside the 24-hour customer-service window. Outside it, Meta requires an approved *template*
message. Personal WhatsApp accounts cannot be automated: there is no browser automation and no
WhatsApp Web session scraping."""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotConfiguredError, UpstreamError, ValidationFailedError
from app.database import repositories as repo
from app.integrations.credentials import CredentialStore

E164 = re.compile(r"^\+?[1-9]\d{7,14}$")


class WhatsAppSendResult(BaseModel):
    message_id: str | None
    to: str
    kind: str


def normalize_phone(value: str) -> str:
    digits = re.sub(r"[\s()-]", "", value)
    if not E164.match(digits):
        raise ValidationFailedError("Phone number must be in international format, e.g. +919876543210")
    return digits.lstrip("+")


def verify_webhook_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


class WhatsAppClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_version: str,
        phone_number_id: str,
        access_token: str,
        timeout: float = 15.0,
    ) -> None:
        self.http = http
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.timeout = timeout

    async def _send(self, payload: dict[str, Any], to: str, kind: str) -> WhatsAppSendResult:
        try:
            res = await self.http.post(self.url, json=payload, headers=self.headers, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise UpstreamError("WhatsApp Cloud API is unreachable") from exc
        data = res.json() if res.content else {}
        if res.status_code >= 400:
            err = (data.get("error") or {}) if isinstance(data, dict) else {}
            code = err.get("code")
            message = err.get("message", f"HTTP {res.status_code}")
            if code == 131047:
                message = "More than 24 hours since the recipient last replied; an approved template is required"
            raise UpstreamError(f"WhatsApp: {message}", code="whatsapp_error", details={"meta_code": code})
        messages = data.get("messages") or [{}]
        return WhatsAppSendResult(message_id=messages[0].get("id"), to=to, kind=kind)

    async def send_text(self, to: str, body: str) -> WhatsAppSendResult:
        recipient = normalize_phone(to)
        if not body.strip():
            raise ValidationFailedError("Message body is empty")
        return await self._send(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": body[:4096]},
            },
            recipient,
            "text",
        )

    async def send_template(
        self, to: str, template: str, language: str = "en_US", parameters: list[str] | None = None
    ) -> WhatsAppSendResult:
        recipient = normalize_phone(to)
        tpl: dict[str, Any] = {"name": template, "language": {"code": language}}
        if parameters:
            tpl["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": p[:1024]} for p in parameters]}
            ]
        return await self._send(
            {"messaging_product": "whatsapp", "to": recipient, "type": "template", "template": tpl},
            recipient,
            "template",
        )


class WhatsAppService:
    def __init__(self, store: CredentialStore, http: httpx.AsyncClient, api_version: str) -> None:
        self.store = store
        self.http = http
        self.api_version = api_version

    async def client_for(self, session: AsyncSession, user_id: uuid.UUID) -> WhatsAppClient:
        integ = await repo.get_integration(session, user_id, "whatsapp")
        if integ is None or integ.status != "connected":
            raise NotConfiguredError(
                "WhatsApp Business is not connected. Configure it in Integrations.", code="whatsapp_not_connected"
            )
        creds = self.store.load(integ)
        phone_number_id = (integ.config or {}).get("phone_number_id")
        if not phone_number_id or not creds.get("access_token"):
            raise NotConfiguredError("WhatsApp configuration is incomplete", code="whatsapp_incomplete")
        return WhatsAppClient(
            self.http, api_version=self.api_version, phone_number_id=phone_number_id, access_token=creds["access_token"]
        )
