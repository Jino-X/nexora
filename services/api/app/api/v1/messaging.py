"""Direct Gmail and WhatsApp endpoints. A user acting from the UI is acting for themselves, so
these run without the assistant's approval step. Every action is audited."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser, ServicesDep, client_meta
from app.database import repositories as repo
from app.integrations.gmail.client import DraftResult, EmailDetail, EmailSummary
from app.integrations.whatsapp.client import WhatsAppSendResult

gmail = APIRouter(prefix="/gmail", tags=["gmail"])
whatsapp = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@gmail.get("/messages", response_model=list[EmailSummary])
async def list_messages(
    user: CurrentUser,
    db: DB,
    services: ServicesDep,
    q: str = Query("", max_length=300),
    unread: bool = False,
    limit: int = Query(15, ge=1, le=25),
) -> list[EmailSummary]:
    client = await services.gmail.client_for(db, user.id)
    query = " ".join(x for x in ("is:unread in:inbox" if unread else "", q) if x)
    return await client.list_messages(query, limit)


@gmail.get("/messages/{message_id}", response_model=EmailDetail)
async def get_message(message_id: str, user: CurrentUser, db: DB, services: ServicesDep) -> EmailDetail:
    client = await services.gmail.client_for(db, user.id)
    return await client.get_message(message_id)


class DraftIn(BaseModel):
    to: str = Field(max_length=320)
    subject: str = Field(max_length=250)
    body: str = Field(max_length=20000)
    cc: str | None = Field(None, max_length=1000)


@gmail.post("/drafts", response_model=DraftResult, status_code=201)
async def create_draft(
    body: DraftIn, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> DraftResult:
    client = await services.gmail.client_for(db, user.id)
    draft = await client.create_draft(body.to, body.subject, body.body, body.cc)
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="gmail.draft_created",
        resource_type="gmail_draft",
        resource_id=draft.draft_id,
        ip=ip,
        user_agent=ua,
    )
    return draft


@gmail.post("/drafts/{draft_id}/send")
async def send_draft(
    draft_id: str, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> dict[str, str | None]:
    client = await services.gmail.client_for(db, user.id)
    result = await client.send_draft(draft_id)
    ip, ua = client_meta(request)
    await repo.audit(
        db, user.id, action="gmail.sent", resource_type="gmail_draft", resource_id=draft_id, ip=ip, user_agent=ua
    )
    return result


class WhatsAppMessageIn(BaseModel):
    to: str = Field(max_length=20)
    message: str | None = Field(None, max_length=4096)
    template: str | None = Field(None, max_length=512, pattern=r"^[a-z0-9_]+$")
    template_language: str = Field("en_US", max_length=10)
    template_parameters: list[str] | None = Field(None, max_length=10)


@whatsapp.post("/messages", response_model=WhatsAppSendResult)
async def send_whatsapp(
    body: WhatsAppMessageIn, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> WhatsAppSendResult:
    services.rate_limiter.check(f"whatsapp:{user.id}", 20)
    client = await services.whatsapp.client_for(db, user.id)
    if body.template:
        result = await client.send_template(body.to, body.template, body.template_language, body.template_parameters)
    else:
        from app.core.exceptions import ValidationFailedError

        if not body.message:
            raise ValidationFailedError("Provide a message or a template")
        result = await client.send_text(body.to, body.message)
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="whatsapp.sent",
        resource_type="whatsapp_message",
        resource_id=result.message_id,
        ip=ip,
        user_agent=ua,
        details={"kind": result.kind},
    )
    return result
