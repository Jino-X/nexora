"""Tasks, approvals, notifications, tool permissions and the dashboard summary."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, ServicesDep, client_meta
from app.assistant import approvals as approval_service
from app.automations.schedule import describe, parse_schedule
from app.database import models as m
from app.database import repositories as repo
from app.schemas.common import OkResponse, Page
from app.schemas.resources import (
    ApprovalOut,
    ConversationOut,
    MarkReadIn,
    NotificationOut,
    TaskRunOut,
    ToolPermissionOut,
    ToolPermissionUpdate,
)

tasks = APIRouter(prefix="/tasks", tags=["tasks"])
approvals = APIRouter(prefix="/approvals", tags=["approvals"])
notifications = APIRouter(prefix="/notifications", tags=["notifications"])
permissions = APIRouter(prefix="/permissions", tags=["permissions"])
dashboard = APIRouter(prefix="/dashboard", tags=["dashboard"])


@tasks.get("", response_model=Page[TaskRunOut])
async def list_tasks(
    user: CurrentUser,
    db: DB,
    status: str | None = Query(None, max_length=24),
    kind: str | None = Query(None, max_length=32),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[TaskRunOut]:
    stmt = select(m.TaskRun).where(m.TaskRun.user_id == user.id)
    if status:
        stmt = stmt.where(m.TaskRun.status == status)
    if kind:
        stmt = stmt.where(m.TaskRun.kind == kind)
    rows, more = await repo.paginate(db, stmt.order_by(m.TaskRun.created_at.desc()), limit, offset)
    return Page.of([TaskRunOut.model_validate(r) for r in rows], more, offset, limit)


@tasks.get("/{task_id}", response_model=TaskRunOut)
async def get_task(task_id: uuid.UUID, user: CurrentUser, db: DB) -> TaskRunOut:
    return TaskRunOut.model_validate(await repo.get_owned(db, m.TaskRun, user.id, task_id, label="Task"))


@approvals.get("", response_model=Page[ApprovalOut])
async def list_approvals(
    user: CurrentUser,
    db: DB,
    status: str | None = Query(None, max_length=16),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[ApprovalOut]:
    stmt = select(m.Approval).where(m.Approval.user_id == user.id)
    if status:
        stmt = stmt.where(m.Approval.status == status)
    rows, more = await repo.paginate(db, stmt.order_by(m.Approval.created_at.desc()), limit, offset)
    return Page.of([ApprovalOut.model_validate(r) for r in rows], more, offset, limit)


@approvals.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve(approval_id: uuid.UUID, request: Request, user: CurrentUser, services: ServicesDep) -> ApprovalOut:
    ip, ua = client_meta(request)
    return ApprovalOut.model_validate(
        await approval_service.approve(services, user.id, approval_id, ip=ip, user_agent=ua)
    )


@approvals.post("/{approval_id}/reject", response_model=ApprovalOut)
async def reject(approval_id: uuid.UUID, request: Request, user: CurrentUser, services: ServicesDep) -> ApprovalOut:
    ip, ua = client_meta(request)
    return ApprovalOut.model_validate(
        await approval_service.reject(services, user.id, approval_id, ip=ip, user_agent=ua)
    )


@notifications.get("", response_model=Page[NotificationOut])
async def list_notifications(
    user: CurrentUser, db: DB, unread: bool = False, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Page[NotificationOut]:
    stmt = select(m.Notification).where(m.Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(m.Notification.read_at.is_(None))
    rows, more = await repo.paginate(db, stmt.order_by(m.Notification.created_at.desc()), limit, offset)
    return Page.of([NotificationOut.model_validate(r) for r in rows], more, offset, limit)


@notifications.get("/unread-count")
async def unread_count(user: CurrentUser, db: DB) -> dict[str, int]:
    return {"count": await repo.unread_notification_count(db, user.id)}


@notifications.post("/read", response_model=OkResponse)
async def mark_read(body: MarkReadIn, user: CurrentUser, db: DB) -> OkResponse:
    count = await repo.mark_notifications_read(db, user.id, body.ids)
    return OkResponse(detail=f"{count} marked read")


@permissions.get("/tools", response_model=list[ToolPermissionOut])
async def list_tool_permissions(user: CurrentUser, db: DB, services: ServicesDep) -> list[ToolPermissionOut]:
    perms = await repo.tool_permissions(db, user.id)
    out = []
    for spec in services.tools.all():
        perm = perms.get(spec.name)
        default_approval = spec.approval == "always" or (spec.approval == "configurable" and spec.risk != "read")
        out.append(
            ToolPermissionOut(
                tool_name=spec.name,
                category=spec.category,
                description=spec.description,
                risk=spec.risk,
                approval_policy=spec.approval,
                integration=spec.integration,
                enabled=perm.enabled if perm else True,
                requires_approval=True
                if spec.approval == "always"
                else (perm.requires_approval if perm and spec.approval == "configurable" else default_approval),
            )
        )
    return out


@permissions.put("/tools/{tool_name}", response_model=ToolPermissionOut)
async def update_tool_permission(
    tool_name: str, body: ToolPermissionUpdate, request: Request, user: CurrentUser, db: DB, services: ServicesDep
) -> ToolPermissionOut:
    spec = services.tools.get(tool_name)
    if spec is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Unknown tool")
    perms = await repo.tool_permissions(db, user.id)
    perm = perms.get(tool_name)
    if perm is None:
        perm = m.ToolPermission(
            user_id=user.id,
            tool_name=tool_name,
            enabled=True,
            requires_approval=spec.approval == "always" or spec.risk != "read",
        )
        db.add(perm)
    if body.enabled is not None:
        perm.enabled = body.enabled
    if body.requires_approval is not None and spec.approval == "configurable":
        perm.requires_approval = body.requires_approval
    await db.flush()
    ip, ua = client_meta(request)
    await repo.audit(
        db,
        user.id,
        action="permission.updated",
        resource_type="tool",
        resource_id=tool_name,
        ip=ip,
        user_agent=ua,
        details=body.model_dump(exclude_none=True),
    )
    return ToolPermissionOut(
        tool_name=spec.name,
        category=spec.category,
        description=spec.description,
        risk=spec.risk,
        approval_policy=spec.approval,
        integration=spec.integration,
        enabled=perm.enabled,
        requires_approval=True if spec.approval == "always" else perm.requires_approval,
    )


@dashboard.get("")
async def dashboard_summary(user: CurrentUser, db: DB, services: ServicesDep) -> dict[str, Any]:
    conversations, _ = await repo.list_conversations(db, user.id, limit=5, offset=0)
    pending = (
        (
            await db.execute(
                select(m.Approval)
                .where(m.Approval.user_id == user.id, m.Approval.status == "pending")
                .order_by(m.Approval.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    pending_count = (
        await db.execute(
            select(func.count())
            .select_from(m.Approval)
            .where(m.Approval.user_id == user.id, m.Approval.status == "pending")
        )
    ).scalar_one()
    recent_tasks = (
        (
            await db.execute(
                select(m.TaskRun).where(m.TaskRun.user_id == user.id).order_by(m.TaskRun.created_at.desc()).limit(5)
            )
        )
        .scalars()
        .all()
    )
    notes = (
        (
            await db.execute(
                select(m.Notification)
                .where(m.Notification.user_id == user.id, m.Notification.read_at.is_(None))
                .order_by(m.Notification.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    upcoming = (
        (
            await db.execute(
                select(m.AutomationRule)
                .where(
                    m.AutomationRule.user_id == user.id,
                    m.AutomationRule.enabled.is_(True),
                    m.AutomationRule.next_run_at.is_not(None),
                )
                .order_by(m.AutomationRule.next_run_at)
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    briefing_run = (
        await db.execute(
            select(m.TaskRun)
            .join(m.AutomationRule, m.AutomationRule.id == m.TaskRun.automation_id)
            .where(
                m.TaskRun.user_id == user.id,
                m.AutomationRule.kind == "morning_briefing",
                m.TaskRun.status == "succeeded",
            )
            .order_by(m.TaskRun.finished_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    connected = await repo.connected_providers(db, user.id)
    return {
        "recent_conversations": [ConversationOut.model_validate(c).model_dump(mode="json") for c in conversations],
        "pending_approvals": [ApprovalOut.model_validate(a).model_dump(mode="json") for a in pending],
        "pending_approval_count": pending_count,
        "recent_tasks": [TaskRunOut.model_validate(t).model_dump(mode="json") for t in recent_tasks],
        "unread_notifications": [NotificationOut.model_validate(n).model_dump(mode="json") for n in notes],
        "unread_notification_count": await repo.unread_notification_count(db, user.id),
        "upcoming_automations": [
            {
                "id": str(r.id),
                "name": r.name,
                "kind": r.kind,
                "next_run_at": r.next_run_at,
                "schedule": describe(parse_schedule(r.schedule)),
            }
            for r in upcoming
        ],
        "latest_briefing": (briefing_run.result.get("briefing") if briefing_run else None),
        "connected_integrations": sorted(connected),
        "memory_count": await services.memory.count(db, user.id),
    }
