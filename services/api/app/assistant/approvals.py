"""Approval decisions. Executes the stored tool call exactly once, through the same permission
evaluation and executor as the graph."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.executor import execute_tool
from app.assistant.tools import ToolContext
from app.core.exceptions import ConflictError
from app.core.permissions import evaluate
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.database.session import session_scope

if TYPE_CHECKING:
    from app.services import Services


async def _transition(s: AsyncSession, approval: m.Approval, status: str) -> None:
    now = utcnow()
    if approval.status != "pending":
        raise ConflictError(f"This approval is already {approval.status}")
    if approval.expires_at < now:
        approval.status = "expired"
        approval.decided_at = now
        raise ConflictError("This approval has expired")
    result = await s.execute(
        update(m.Approval)
        .where(m.Approval.id == approval.id, m.Approval.user_id == approval.user_id, m.Approval.status == "pending")
        .values(status=status, decided_at=now)
        .execution_options(synchronize_session=False)
    )
    if (result.rowcount or 0) != 1:  # type: ignore[attr-defined]
        raise ConflictError("This approval was already decided")
    approval.status = status
    approval.decided_at = now


async def reject(
    services: Services,
    user_id: uuid.UUID,
    approval_id: uuid.UUID,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> m.Approval:
    async with session_scope(services.sessionmaker) as s:
        approval = await repo.get_owned(s, m.Approval, user_id, approval_id, label="Approval")
        await _transition(s, approval, "rejected")
        await repo.audit(
            s,
            user_id,
            action="approval.rejected",
            resource_type="approval",
            resource_id=str(approval.id),
            ip=ip,
            user_agent=user_agent,
            details={"tool": approval.tool_name},
        )
        if approval.conversation_id:
            conv = await s.get(m.Conversation, approval.conversation_id)
            if conv and conv.user_id == user_id:
                await repo.add_message(
                    s,
                    conv,
                    role="assistant",
                    content="Okay, I cancelled that action.",
                    meta={"approval_id": str(approval.id), "approval_status": "rejected"},
                )
        return approval


async def approve(
    services: Services,
    user_id: uuid.UUID,
    approval_id: uuid.UUID,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> m.Approval:
    async with session_scope(services.sessionmaker) as s:
        approval = await repo.get_owned(s, m.Approval, user_id, approval_id, label="Approval")
        if approval.status == "pending" and approval.expires_at < utcnow():
            approval.status = "expired"
            approval.decided_at = utcnow()
            await s.commit()
            raise ConflictError("This approval has expired")
        await _transition(s, approval, "approved")
        run = m.TaskRun(
            user_id=user_id,
            kind="approval",
            title=approval.summary[:200],
            status="running",
            idempotency_key=f"approval:{approval.id}",
            started_at=utcnow(),
            attempt=1,
            conversation_id=approval.conversation_id,
        )
        s.add(run)
        try:
            await s.flush()
        except IntegrityError as exc:
            raise ConflictError("This approval was already executed") from exc
        approval.task_run_id = run.id
        await repo.audit(
            s,
            user_id,
            action="approval.approved",
            resource_type="approval",
            resource_id=str(approval.id),
            ip=ip,
            user_agent=user_agent,
            details={"tool": approval.tool_name},
        )

    async with session_scope(services.sessionmaker) as s:
        approval = await repo.get_owned(s, m.Approval, user_id, approval_id)
        run = await s.get(m.TaskRun, approval.task_run_id)
        assert run is not None
        spec = services.tools.get(approval.tool_name)
        profile = await s.get(m.Profile, user_id)
        prefs = await repo.get_preferences(s, user_id)
        if spec is None:
            ok, message, card = False, "This action is no longer supported.", None
        else:
            decision = evaluate(
                spec,
                channel="approval",
                permissions=await repo.tool_permissions(s, user_id),
                connected=await repo.connected_providers(s, user_id),
                preferences={"memory_enabled": prefs.memory_enabled},
            )
            if not decision.allowed:
                ok, message, card = False, decision.reason or "Not allowed", None
            else:
                ctx = ToolContext(
                    services=services,
                    session=s,
                    user_id=user_id,
                    conversation_id=approval.conversation_id,
                    run_id=f"approval-{approval.id}",
                    channel="approval",
                    timezone=(profile.timezone if profile else "UTC"),
                    location=None,
                    preferences={},
                )
                result = await execute_tool(ctx, spec, spec.args_model.model_validate(approval.tool_args))
                ok, message, card = result.ok, result.message, result.card
        approval.status = "executed" if ok else "failed"
        approval.result = {"ok": ok, "message": message}
        run.status = "succeeded" if ok else "failed"
        run.finished_at = utcnow()
        run.result = {"message": message}
        run.error = None if ok else message
        if approval.conversation_id:
            conv = await s.get(m.Conversation, approval.conversation_id)
            if conv and conv.user_id == user_id:
                await repo.add_message(
                    s,
                    conv,
                    role="assistant",
                    content=message if ok else f"I couldn't complete that: {message}",
                    status="complete",
                    meta={
                        "approval_id": str(approval.id),
                        "approval_status": approval.status,
                        "cards": [card] if card else [],
                    },
                )
        await repo.notify(
            s,
            user_id,
            kind="approval",
            title="Action completed" if ok else "Action failed",
            body=message,
            data={"approval_id": str(approval.id)},
        )
        return approval
