"""Data access. Every query on user-owned data is filtered by `user_id`: this is the primary
isolation guarantee in the API (RLS is the second line of defence for direct PostgREST access)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import models as m
from app.database.base import Base, utcnow

T = TypeVar("T", bound=Base)


async def get_owned(
    session: AsyncSession, model: type[T], user_id: uuid.UUID, obj_id: uuid.UUID, *, label: str | None = None
) -> T:
    """Fetch a row by id that must belong to `user_id`; other users' rows look like 404s."""
    stmt = select(model).where(model.id == obj_id, model.user_id == user_id)  # type: ignore[attr-defined]
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj is None:
        raise NotFoundError(f"{label or model.__name__} not found")
    return obj


async def paginate(session: AsyncSession, stmt: Select[Any], limit: int, offset: int) -> tuple[list[Any], bool]:
    rows = (await session.execute(stmt.limit(limit + 1).offset(offset))).scalars().all()
    return list(rows[:limit]), len(rows) > limit


# ---- profiles & preferences --------------------------------------------------------------------


async def ensure_profile(session: AsyncSession, user_id: uuid.UUID, email: str | None) -> m.Profile:
    profile = await session.get(m.Profile, user_id)
    if profile is None:
        profile = m.Profile(id=user_id, email=email, display_name=(email or "").split("@")[0] or None)
        session.add(profile)
        session.add(m.UserPreferences(user_id=user_id))
        await session.flush()
    elif email and profile.email != email:
        profile.email = email
    return profile


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> m.UserPreferences:
    prefs = (
        await session.execute(select(m.UserPreferences).where(m.UserPreferences.user_id == user_id))
    ).scalar_one_or_none()
    if prefs is None:
        prefs = m.UserPreferences(user_id=user_id)
        session.add(prefs)
        await session.flush()
    return prefs


# ---- conversations & messages ------------------------------------------------------------------


async def create_conversation(
    session: AsyncSession, user_id: uuid.UUID, *, title: str = "New conversation", channel: str = "text"
) -> m.Conversation:
    conv = m.Conversation(user_id=user_id, title=title[:200], channel=channel, last_message_at=utcnow())
    session.add(conv)
    await session.flush()
    return conv


async def list_conversations(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    q: str | None = None,
    include_archived: bool = False,
) -> tuple[list[m.Conversation], bool]:
    stmt = select(m.Conversation).where(m.Conversation.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(m.Conversation.archived.is_(False))
    if q:
        stmt = stmt.where(m.Conversation.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(m.Conversation.last_message_at.desc())
    return await paginate(session, stmt, limit, offset)


async def recent_messages(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int
) -> list[m.Message]:
    stmt = (
        select(m.Message)
        .where(m.Message.conversation_id == conversation_id, m.Message.user_id == user_id)
        .order_by(m.Message.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(reversed(rows))


async def list_messages(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 200
) -> list[m.Message]:
    stmt = (
        select(m.Message)
        .where(m.Message.conversation_id == conversation_id, m.Message.user_id == user_id)
        .order_by(m.Message.created_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_message(
    session: AsyncSession,
    conv: m.Conversation,
    *,
    role: str,
    content: str,
    status: str = "complete",
    run_id: str | None = None,
    channel: str = "text",
    tool_calls: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> m.Message:
    msg = m.Message(
        conversation_id=conv.id,
        user_id=conv.user_id,
        role=role,
        content=content,
        status=status,
        run_id=run_id,
        channel=channel,
        tool_calls=tool_calls or [],
        meta=meta or {},
    )
    session.add(msg)
    conv.last_message_at = utcnow()
    await session.flush()
    return msg


# ---- permissions ------------------------------------------------------------------------------


async def tool_permissions(session: AsyncSession, user_id: uuid.UUID) -> dict[str, m.ToolPermission]:
    rows = (await session.execute(select(m.ToolPermission).where(m.ToolPermission.user_id == user_id))).scalars()
    return {row.tool_name: row for row in rows}


async def get_integration(session: AsyncSession, user_id: uuid.UUID, provider: str) -> m.Integration | None:
    stmt = select(m.Integration).where(m.Integration.user_id == user_id, m.Integration.provider == provider)
    return (await session.execute(stmt)).scalar_one_or_none()


async def connected_providers(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    stmt = select(m.Integration.provider).where(m.Integration.user_id == user_id, m.Integration.status == "connected")
    return set((await session.execute(stmt)).scalars().all())


# ---- notifications, audit, logs -------------------------------------------------------------------


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str,
    title: str,
    body: str = "",
    data: dict[str, Any] | None = None,
) -> m.Notification:
    note = m.Notification(user_id=user_id, kind=kind, title=title[:200], body=body, data=data or {})
    session.add(note)
    await session.flush()
    return note


async def audit(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor: str = "user",
    ip: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        m.AuditLog(
            user_id=user_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip,
            user_agent=(user_agent or "")[:300] or None,
            details=details or {},
        )
    )
    await session.flush()


async def unread_notification_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(m.Notification)
        .where(m.Notification.user_id == user_id, m.Notification.read_at.is_(None))
    )
    return int((await session.execute(stmt)).scalar_one())


async def mark_notifications_read(
    session: AsyncSession, user_id: uuid.UUID, ids: Sequence[uuid.UUID] | None = None
) -> int:
    stmt = update(m.Notification).where(m.Notification.user_id == user_id, m.Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(m.Notification.id.in_(list(ids)))
    result = await session.execute(stmt.values(read_at=utcnow()))
    return result.rowcount or 0  # type: ignore[attr-defined]


async def expire_stale_approvals(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(
        update(m.Approval)
        .where(m.Approval.status == "pending", m.Approval.expires_at < now)
        .values(status="expired", decided_at=now)
    )
    return result.rowcount or 0  # type: ignore[attr-defined]


async def purge_expired_memories(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(delete(m.Memory).where(m.Memory.expires_at.is_not(None), m.Memory.expires_at < now))
    return result.rowcount or 0  # type: ignore[attr-defined]


async def delete_user_data(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete every row owned by the user. Order respects foreign keys even without cascades."""
    for model in (
        m.Approval,
        m.TaskRun,
        m.AutomationRule,
        m.Message,
        m.Memory,
        m.VoiceSession,
        m.Conversation,
        m.ExecutionLog,
        m.Notification,
        m.VaultItem,
        m.Integration,
        m.OAuthState,
        m.ToolPermission,
        m.AuditLog,
        m.UserPreferences,
    ):
        await session.execute(delete(model).where(model.user_id == user_id))  # type: ignore[attr-defined]
    await session.execute(delete(m.Profile).where(m.Profile.id == user_id))
