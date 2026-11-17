"""Reminder, automation and briefing tools."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.assistant.tools import ToolContext, ToolRegistry, ToolResult, ToolSpec
from app.automations.briefing import build_briefing
from app.automations.schedule import describe, parse_schedule
from app.automations.service import create_rule
from app.core.exceptions import ValidationFailedError
from app.database import models as m


class ReminderArgs(BaseModel):
    message: str = Field(min_length=1, max_length=300, description="What to remind the user about")
    remind_at: str = Field(description="Local date-time in ISO format YYYY-MM-DDTHH:MM, in the user's timezone")


async def reminder_create(ctx: ToolContext, args: ReminderArgs) -> ToolResult:
    try:
        at = datetime.fromisoformat(args.remind_at)
    except ValueError as exc:
        raise ValidationFailedError("remind_at must look like 2026-11-15T09:00") from exc
    at = at.replace(tzinfo=None, second=0, microsecond=0)
    rule = await create_rule(
        ctx.session,
        ctx.user_id,
        name=f"Reminder: {args.message[:60]}",
        kind="reminder",
        schedule={"type": "once", "at": at.isoformat()},
        timezone=ctx.timezone,
        config={"message": args.message},
    )
    when = at.strftime("%a %d %b at %H:%M")
    return ToolResult(
        ok=True,
        message=f"Reminder set for {when}: {args.message}.",
        data={"id": str(rule.id), "when": when, "timezone": ctx.timezone},
        card={"type": "reminder", "id": str(rule.id), "message": args.message, "when": when},
    )


class AutomationArgs(BaseModel):
    kind: Literal["morning_briefing", "news_summary", "email_summary", "assistant_prompt"]
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Local time HH:MM")
    days: list[int] | None = Field(None, description="Weekdays 0=Mon..6=Sun; omit for every day")
    name: str | None = Field(None, max_length=120)
    prompt: str | None = Field(None, max_length=2000, description="Required for assistant_prompt")


async def automation_create(ctx: ToolContext, args: AutomationArgs) -> ToolResult:
    schedule = (
        {"type": "weekly", "time": args.time, "days": args.days} if args.days else {"type": "daily", "time": args.time}
    )
    config = {"prompt": args.prompt} if args.kind == "assistant_prompt" else {}
    rule = await create_rule(
        ctx.session,
        ctx.user_id,
        name=args.name or args.kind.replace("_", " ").title(),
        kind=args.kind,
        schedule=schedule,
        timezone=ctx.timezone,
        config=config,
    )
    desc = describe(parse_schedule(rule.schedule))
    return ToolResult(
        ok=True,
        message=f"Created '{rule.name}', running {desc}.",
        data={"id": str(rule.id), "schedule": desc},
        card={"type": "automation", "id": str(rule.id), "name": rule.name, "schedule": desc},
    )


class EmptyArgs(BaseModel):
    pass


async def automation_list(ctx: ToolContext, args: EmptyArgs) -> ToolResult:
    rows = (
        (
            await ctx.session.execute(
                select(m.AutomationRule)
                .where(m.AutomationRule.user_id == ctx.user_id)
                .order_by(m.AutomationRule.next_run_at)
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    data = [
        {
            "name": r.name,
            "kind": r.kind,
            "enabled": r.enabled,
            "schedule": describe(parse_schedule(r.schedule)),
            "next_run_at": r.next_run_at,
        }
        for r in rows
    ]
    return ToolResult(ok=True, message=f"You have {len(rows)} automation(s).", data=data)


async def briefing_generate(ctx: ToolContext, args: EmptyArgs) -> ToolResult:
    briefing = await build_briefing(ctx.services, ctx.session, ctx.user_id, use_llm=False)
    return ToolResult(
        ok=True, message=briefing["text"], data=briefing["sections"], card={"type": "briefing", "briefing": briefing}
    )


def register(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="reminder_create",
            category="automation",
            args_model=ReminderArgs,
            handler=reminder_create,
            risk="write",
            description="Create a one-time reminder at a specific local date and time.",
        )
    )
    registry.register(
        ToolSpec(
            name="automation_create",
            category="automation",
            args_model=AutomationArgs,
            handler=automation_create,
            risk="write",
            channels=("text", "voice"),
            description="Create a recurring automation: daily morning briefing, news summary, email summary or a "
            "scheduled assistant prompt.",
        )
    )
    registry.register(
        ToolSpec(
            name="automation_list",
            category="automation",
            args_model=EmptyArgs,
            handler=automation_list,
            description="List the user's reminders and automations.",
        )
    )
    registry.register(
        ToolSpec(
            name="briefing_generate",
            category="automation",
            args_model=EmptyArgs,
            handler=briefing_generate,
            description="Build the user's briefing now: weather, top headlines, unread emails and today's reminders.",
        )
    )
