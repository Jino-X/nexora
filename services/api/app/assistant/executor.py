"""Runs one authorized tool call with a timeout, uniform error handling and execution logging."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from app.assistant.tools import ToolContext, ToolResult, ToolSpec
from app.core.exceptions import AppError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow

logger = logging.getLogger("nexora.tools")

APPROVAL_TTL = timedelta(hours=24)


async def execute_tool(ctx: ToolContext, spec: ToolSpec, args: BaseModel) -> ToolResult:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(spec.handler(ctx, args), timeout=spec.timeout_seconds)
    except TimeoutError:
        result = ToolResult(ok=False, message=f"{spec.name} timed out", error_code="timeout")
    except AppError as exc:
        result = ToolResult(ok=False, message=exc.message, error_code=exc.code)
    except Exception:
        logger.exception("tool %s crashed", spec.name)
        result = ToolResult(ok=False, message=f"{spec.name} failed unexpectedly", error_code="tool_error")
    if not isinstance(result, ToolResult):
        result = ToolResult(ok=False, message=f"{spec.name} returned an invalid result", error_code="invalid_result")
    duration = int((time.perf_counter() - started) * 1000)
    ctx.session.add(
        m.ExecutionLog(
            user_id=ctx.user_id,
            run_id=ctx.run_id,
            conversation_id=ctx.conversation_id,
            event_type="tool_call",
            name=spec.name,
            status="ok" if result.ok else "error",
            duration_ms=duration,
            details={"channel": ctx.channel, "args": _safe_args(spec, args)},
            error=None if result.ok else result.message[:500],
        )
    )
    return result


def _safe_args(spec: ToolSpec, args: BaseModel) -> dict[str, Any]:
    """Log argument *shapes* for sensitive tools and full args for read-only ones."""
    data = args.model_dump(mode="json", exclude_none=True)
    if spec.risk == "read":
        return data
    return {k: (f"<{len(v)} chars>" if isinstance(v, str) and len(v) > 40 else v) for k, v in data.items()}


async def create_approval(ctx: ToolContext, spec: ToolSpec, args: BaseModel) -> m.Approval:
    summary = spec.approval_summary(args)
    approval = m.Approval(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        tool_name=spec.name,
        tool_args=args.model_dump(mode="json"),
        summary=summary,
        status="pending",
        expires_at=utcnow() + APPROVAL_TTL,
    )
    ctx.session.add(approval)
    await ctx.session.flush()
    await repo.notify(
        ctx.session,
        ctx.user_id,
        kind="approval",
        title="Approval needed",
        body=summary,
        data={"approval_id": str(approval.id), "tool": spec.name},
    )
    await repo.audit(
        ctx.session,
        ctx.user_id,
        actor="assistant",
        action="approval.requested",
        resource_type="approval",
        resource_id=str(approval.id),
        details={"tool": spec.name},
    )
    return approval
