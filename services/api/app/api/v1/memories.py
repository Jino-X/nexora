from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import delete, select

from app.api.deps import DB, CurrentUser, ServicesDep
from app.database import models as m
from app.database import repositories as repo
from app.schemas.common import OkResponse, Page
from app.schemas.resources import MemoryCreate, MemoryOut, MemoryUpdate

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=Page[MemoryOut])
async def list_memories(
    user: CurrentUser,
    db: DB,
    services: ServicesDep,
    q: str | None = Query(None, max_length=300),
    kind: str | None = Query(None, max_length=32),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[MemoryOut]:
    if q:
        hits = await services.memory.search(db, user.id, q, limit=limit, min_score=0.15)
        items = []
        for mem, score in hits:
            out = MemoryOut.model_validate(mem)
            out.score = round(score, 3)
            items.append(out)
        return Page(items=items, has_more=False)
    rows, more = await services.memory.list(db, user.id, kind=kind, limit=limit, offset=offset)
    return Page.of([MemoryOut.model_validate(r) for r in rows], more, offset, limit)


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(body: MemoryCreate, user: CurrentUser, db: DB, services: ServicesDep) -> MemoryOut:
    prefs = await repo.get_preferences(db, user.id)
    mem = await services.memory.create(
        db,
        user.id,
        body.content,
        kind=body.kind,
        source="user",
        importance=body.importance,
        pinned=body.pinned,
        retention_days=prefs.memory_retention_days,
    )
    return MemoryOut.model_validate(mem)


@router.get("/export")
async def export_memories(user: CurrentUser, db: DB) -> dict[str, Any]:
    rows = (
        (await db.execute(select(m.Memory).where(m.Memory.user_id == user.id).order_by(m.Memory.created_at)))
        .scalars()
        .all()
    )
    return {"memories": [MemoryOut.model_validate(r).model_dump(mode="json") for r in rows]}


@router.post("/reindex")
async def reindex(user: CurrentUser, db: DB, services: ServicesDep) -> dict[str, int]:
    return {"reindexed": await services.memory.reindex(db, user.id)}


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: uuid.UUID, body: MemoryUpdate, user: CurrentUser, db: DB, services: ServicesDep
) -> MemoryOut:
    mem = await services.memory.update(db, user.id, memory_id, body.model_dump(exclude_unset=True))
    return MemoryOut.model_validate(mem)


@router.delete("/{memory_id}", response_model=OkResponse)
async def delete_memory(memory_id: uuid.UUID, user: CurrentUser, db: DB) -> OkResponse:
    mem = await repo.get_owned(db, m.Memory, user.id, memory_id, label="Memory")
    await db.delete(mem)
    return OkResponse()


@router.delete("", response_model=OkResponse)
async def delete_all_memories(user: CurrentUser, db: DB, confirm: bool = Query(False)) -> OkResponse:
    if not confirm:
        from app.core.exceptions import ValidationFailedError

        raise ValidationFailedError("Pass confirm=true to delete all memories")
    result = await db.execute(delete(m.Memory).where(m.Memory.user_id == user.id))
    await repo.audit(db, user.id, action="memory.deleted_all", resource_type="memory")
    return OkResponse(detail=f"Deleted {result.rowcount or 0} memories")  # type: ignore[attr-defined]
