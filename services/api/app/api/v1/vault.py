"""Secure vault. Values are only returned by POST /vault/{id}/reveal, which is rate limited,
optionally needs a recent sign-in, and is always audited."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, ServicesDep, client_meta
from app.core.exceptions import PermissionDeniedError
from app.database import models as m
from app.database import repositories as repo
from app.schemas.common import OkResponse, Page
from app.schemas.resources import AuditLogOut, VaultItemCreate, VaultItemOut, VaultItemUpdate, VaultReveal

router = APIRouter(prefix="/vault", tags=["vault"])


@router.get("/status")
async def vault_status(user: CurrentUser, services: ServicesDep) -> dict[str, object]:
    return {
        "configured": services.vault.cipher is not None,
        "key_provider": services.settings.key_provider,
        "reauth_minutes": services.settings.vault_reauth_max_age_minutes,
    }


@router.get("", response_model=list[VaultItemOut])
async def list_items(user: CurrentUser, db: DB, q: str | None = Query(None, max_length=100)) -> list[VaultItemOut]:
    stmt = select(m.VaultItem).where(m.VaultItem.user_id == user.id)
    if q:
        stmt = stmt.where(m.VaultItem.name.ilike(f"%{q}%"))
    rows = (await db.execute(stmt.order_by(m.VaultItem.name))).scalars().all()
    return [VaultItemOut.model_validate(r) for r in rows]


@router.post("", response_model=VaultItemOut, status_code=201)
async def create_item(
    body: VaultItemCreate, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> VaultItemOut:
    item = await services.vault.create(
        db,
        user.id,
        name=body.name,
        kind=body.kind,
        description=body.description,
        secret=body.secret,
        fields=body.fields,
        file_base64=body.file_base64,
        content_type=body.content_type,
    )
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="vault.created",
        resource_type="vault_item",
        resource_id=str(item.id),
        ip=ip,
        user_agent=ua,
        details={"kind": item.kind},
    )
    return VaultItemOut.model_validate(item)


@router.post("/{item_id}/reveal", response_model=VaultReveal)
async def reveal_item(
    item_id: uuid.UUID, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> VaultReveal:
    services.rate_limiter.check(f"vault-reveal:{user.id}", 10)
    max_age = services.settings.vault_reauth_max_age_minutes
    if max_age:
        age = user.last_sign_in_age_seconds()
        if age is None or age > max_age * 60:
            raise PermissionDeniedError("Please sign in again to reveal vault items", code="reauth_required")
    payload = await services.vault.reveal(db, user.id, item_id)
    item = await repo.get_owned(db, m.VaultItem, user.id, item_id, label="Vault item")
    ip, ua = client_meta(request)
    await repo.audit(
        db, user.id, action="vault.revealed", resource_type="vault_item", resource_id=str(item_id), ip=ip, user_agent=ua
    )
    return VaultReveal(
        id=item.id,
        name=item.name,
        kind=item.kind,
        secret=payload.get("secret"),
        fields=payload.get("fields"),
        file_base64=payload.get("file_base64"),
        content_type=item.content_type,
    )


@router.patch("/{item_id}", response_model=VaultItemOut)
async def update_item(
    item_id: uuid.UUID, body: VaultItemUpdate, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> VaultItemOut:
    item = await services.vault.update(db, user.id, item_id, **body.model_dump(exclude_none=True))
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="vault.updated",
        resource_type="vault_item",
        resource_id=str(item_id),
        ip=ip,
        user_agent=ua,
        details={"fields": sorted(body.model_dump(exclude_none=True))},
    )
    return VaultItemOut.model_validate(item)


@router.delete("/{item_id}", response_model=OkResponse)
async def delete_item(item_id: uuid.UUID, request: Request, user: CurrentUser, db: DB) -> OkResponse:
    item = await repo.get_owned(db, m.VaultItem, user.id, item_id, label="Vault item")
    await db.delete(item)
    ip, ua = client_meta(request)
    await repo.audit(
        db, user.id, action="vault.deleted", resource_type="vault_item", resource_id=str(item_id), ip=ip, user_agent=ua
    )
    return OkResponse()


@router.get("/audit", response_model=Page[AuditLogOut])
async def audit_trail(
    user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
) -> Page[AuditLogOut]:
    stmt = select(m.AuditLog).where(m.AuditLog.user_id == user.id).order_by(m.AuditLog.created_at.desc())
    rows, more = await repo.paginate(db, stmt, limit, offset)
    return Page.of([AuditLogOut.model_validate(r) for r in rows], more, offset, limit)
