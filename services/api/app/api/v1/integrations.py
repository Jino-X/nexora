"""Integration status, Gmail OAuth, WhatsApp configuration and webhook, disconnect."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, ServicesDep, client_meta
from app.core.exceptions import AppError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.database import models as m
from app.database import repositories as repo
from app.integrations.whatsapp.client import verify_webhook_signature
from app.schemas.common import OkResponse
from app.schemas.resources import IntegrationStatus, WhatsAppConfigIn

router = APIRouter(prefix="/integrations", tags=["integrations"])
logger = logging.getLogger("nexora.integrations")

CATALOG: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail",
        "kind": "per_user",
        "description": "Read, search and summarise email; drafts and sending need your approval.",
        "hint": "Server needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (Google Cloud OAuth client).",
    },
    "whatsapp": {
        "name": "WhatsApp Business",
        "kind": "per_user",
        "description": "Send messages from your WhatsApp Business number via the official Cloud API.",
        "hint": "Needs a WhatsApp Business Platform phone number ID and access token from Meta.",
    },
    "youtube": {
        "name": "YouTube",
        "kind": "server",
        "description": "Search videos and channels; play with the official embedded player.",
        "hint": "Server needs YOUTUBE_API_KEY (YouTube Data API v3).",
    },
    "music": {
        "name": "Music",
        "kind": "server",
        "description": "Find songs and playlists with official previews, links and embeds.",
        "hint": "Uses Apple's iTunes Search API; set SPOTIFY_CLIENT_ID/SECRET for Spotify.",
    },
    "weather": {"name": "Weather", "kind": "server", "description": "Open-Meteo forecasts.", "hint": None},
    "maps": {
        "name": "Maps & places",
        "kind": "server",
        "description": "OpenStreetMap geocoding and nearby search.",
        "hint": None,
    },
    "news": {"name": "News", "kind": "server", "description": "RSS headlines with source attribution.", "hint": None},
}


def _tools_for(services: Any, category: str) -> list[str]:
    return [t.name for t in services.tools.all() if t.category == category or t.integration == category]


@router.get("", response_model=list[IntegrationStatus])
async def list_integrations(user: CurrentUser, db: DB, services: ServicesDep) -> list[IntegrationStatus]:
    rows = {
        i.provider: i
        for i in (await db.execute(select(m.Integration).where(m.Integration.user_id == user.id))).scalars()
    }
    s = services.settings
    available = {
        "gmail": s.google_configured and services.cipher is not None,
        "whatsapp": services.cipher is not None,
        "youtube": services.youtube.configured,
        "music": True,
        "weather": True,
        "maps": True,
        "news": True,
    }
    out = []
    for provider, info in CATALOG.items():
        row = rows.get(provider)
        if info["kind"] == "server":
            status = "ready" if available[provider] else "not_configured"
        elif not available[provider]:
            status = "not_configured"
        else:
            status = row.status if row else "disconnected"
        out.append(
            IntegrationStatus(
                provider=provider,
                name=info["name"],
                description=info["description"],
                kind=info["kind"],
                available=available[provider],
                status=status,
                account_label=row.account_label if row else None,
                scopes=row.scopes if row else [],
                connected_at=row.connected_at if row else None,
                last_error=row.last_error if row else None,
                setup_hint=None if available[provider] else info["hint"],
                tools=_tools_for(services, "location" if provider == "maps" else provider),
            )
        )
    return out


@router.post("/gmail/connect")
async def gmail_connect(user: CurrentUser, db: DB, services: ServicesDep) -> dict[str, str]:
    if services.cipher is None:
        raise ValidationFailedError("Credential encryption is not configured on the server")
    return {"authorization_url": await services.google_oauth.authorization_url(db, user.id)}


@router.get("/gmail/callback", include_in_schema=False)
async def gmail_callback(
    db: DB,
    services: ServicesDep,
    state: str = Query(..., max_length=128),
    code: str | None = Query(None, max_length=2048),
    error: str | None = Query(None, max_length=200),
) -> RedirectResponse:
    target = f"{services.settings.web_app_url}/integrations/gmail"
    try:
        oauth_state = await services.google_oauth.consume_state(db, state)
        if error or not code:
            await db.commit()
            return RedirectResponse(f"{target}?{urlencode({'status': 'error', 'reason': error or 'cancelled'})}")
        token = await services.google_oauth.exchange_code(code, oauth_state.code_verifier)
        email = await services.gmail.complete_connection(db, oauth_state.user_id, token)
        await repo.audit(
            db,
            oauth_state.user_id,
            action="integration.connected",
            resource_type="integration",
            resource_id="gmail",
            details={"account": email},
        )
        await repo.notify(
            db, oauth_state.user_id, kind="integration", title="Gmail connected", body=f"Nexora can now read {email}."
        )
        await db.commit()
        return RedirectResponse(f"{target}?status=connected")
    except AppError as exc:
        await db.rollback()
        logger.warning("gmail oauth failed: %s", exc.code)
        return RedirectResponse(f"{target}?{urlencode({'status': 'error', 'reason': exc.code})}")


@router.put("/whatsapp", response_model=IntegrationStatus)
async def configure_whatsapp(
    body: WhatsAppConfigIn, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> IntegrationStatus:
    integ = await services.credentials.save(
        db,
        user.id,
        "whatsapp",
        {"access_token": body.access_token},
        account_label=body.display_phone_number or f"Phone number ID {body.phone_number_id}",
        config={"phone_number_id": body.phone_number_id, "business_account_id": body.business_account_id},
    )
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="integration.connected",
        resource_type="integration",
        resource_id="whatsapp",
        ip=ip,
        user_agent=ua,
    )
    info = CATALOG["whatsapp"]
    return IntegrationStatus(
        provider="whatsapp",
        name=info["name"],
        description=info["description"],
        kind="per_user",
        available=True,
        status=integ.status,
        account_label=integ.account_label,
        connected_at=integ.connected_at,
        tools=_tools_for(services, "whatsapp"),
    )


@router.post("/{provider}/disconnect", response_model=OkResponse)
async def disconnect(provider: str, request: Request, user: CurrentUser, db: DB, services: ServicesDep) -> OkResponse:
    integ = await repo.get_integration(db, user.id, provider)
    if integ is None:
        raise NotFoundError("Integration not connected")
    if provider == "gmail" and integ.credentials_ciphertext and services.cipher:
        try:
            creds = services.credentials.load(integ)
            await services.google_oauth.revoke(creds.get("refresh_token") or creds.get("access_token", ""))
        except AppError:
            pass
    await services.credentials.disconnect(db, integ)
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="integration.disconnected",
        resource_type="integration",
        resource_id=provider,
        ip=ip,
        user_agent=ua,
    )
    return OkResponse()


# ---- WhatsApp webhook (Meta -> Nexora) -----------------------------------------------------------


@router.get("/whatsapp/webhook", response_class=PlainTextResponse, include_in_schema=False)
async def whatsapp_verify(
    services: ServicesDep,
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
) -> str:
    expected = services.settings.whatsapp_webhook_verify_token
    if mode == "subscribe" and expected and token == expected.get_secret_value():
        return challenge
    raise PermissionDeniedError("Webhook verification failed")


@router.post("/whatsapp/webhook", response_model=OkResponse, include_in_schema=False)
async def whatsapp_webhook(
    request: Request, db: DB, services: ServicesDep, x_hub_signature_256: Annotated[str | None, Header()] = None
) -> OkResponse:
    secret = services.settings.whatsapp_app_secret
    body = await request.body()
    if not secret or not verify_webhook_signature(secret.get_secret_value(), body, x_hub_signature_256):
        raise PermissionDeniedError("Invalid webhook signature")
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            phone_id = (value.get("metadata") or {}).get("phone_number_id")
            if not phone_id:
                continue
            integrations = (
                (
                    await db.execute(
                        select(m.Integration).where(
                            m.Integration.provider == "whatsapp", m.Integration.status == "connected"
                        )
                    )
                )
                .scalars()
                .all()
            )
            owner = next((i for i in integrations if (i.config or {}).get("phone_number_id") == phone_id), None)
            if owner is None:
                continue
            for msg in value.get("messages", [])[:20]:
                preview = ((msg.get("text") or {}).get("body") or f"[{msg.get('type', 'message')}]")[:140]
                await repo.notify(
                    db,
                    owner.user_id,
                    kind="integration",
                    title=f"WhatsApp from +{msg.get('from')}",
                    body=preview,
                    data={"provider": "whatsapp", "from": msg.get("from")},
                )
    return OkResponse()
