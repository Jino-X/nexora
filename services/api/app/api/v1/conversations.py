from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.database import models as m
from app.database import repositories as repo
from app.schemas.common import OkResponse, Page
from app.schemas.resources import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=Page[ConversationOut])
async def list_conversations(
    user: CurrentUser,
    db: DB,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=100),
    include_archived: bool = False,
) -> Page[ConversationOut]:
    rows, more = await repo.list_conversations(
        db, user.id, limit=limit, offset=offset, q=q, include_archived=include_archived
    )
    return Page.of([ConversationOut.model_validate(r) for r in rows], more, offset, limit)


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreate, user: CurrentUser, db: DB) -> ConversationOut:
    return ConversationOut.model_validate(await repo.create_conversation(db, user.id, title=body.title))


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DB) -> ConversationDetail:
    conv = await repo.get_owned(db, m.Conversation, user.id, conversation_id, label="Conversation")
    messages = await repo.list_messages(db, user.id, conv.id)
    return ConversationDetail(
        conversation=ConversationOut.model_validate(conv), messages=[MessageOut.model_validate(x) for x in messages]
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, user: CurrentUser, db: DB
) -> ConversationOut:
    conv = await repo.get_owned(db, m.Conversation, user.id, conversation_id, label="Conversation")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(conv, key, value)
    await db.flush()
    return ConversationOut.model_validate(conv)


@router.delete("/{conversation_id}", response_model=OkResponse)
async def delete_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DB) -> OkResponse:
    conv = await repo.get_owned(db, m.Conversation, user.id, conversation_id, label="Conversation")
    await db.delete(conv)
    return OkResponse()
