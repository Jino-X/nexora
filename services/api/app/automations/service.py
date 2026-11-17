"""Automation rule management (validation + next-run bookkeeping)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automations.schedule import next_run_after, parse_schedule, zone
from app.core.exceptions import ValidationFailedError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow

AUTOMATION_KINDS = ("morning_briefing", "news_summary", "email_summary", "reminder", "assistant_prompt")
MAX_RULES_PER_USER = 100


def validate_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    if kind not in AUTOMATION_KINDS:
        raise ValidationFailedError(f"Unknown automation kind '{kind}'", details={"allowed": AUTOMATION_KINDS})
    clean: dict[str, Any] = {}
    if kind == "reminder":
        message = str(config.get("message", "")).strip()
        if not message:
            raise ValidationFailedError("A reminder needs a message")
        clean["message"] = message[:500]
    elif kind == "assistant_prompt":
        prompt = str(config.get("prompt", "")).strip()
        if not prompt:
            raise ValidationFailedError("A scheduled assistant action needs a prompt")
        clean["prompt"] = prompt[:2000]
    elif kind == "news_summary":
        cats = config.get("categories") or []
        clean["categories"] = [str(c)[:32] for c in cats][:6]
    if kind in ("morning_briefing", "news_summary", "email_summary"):
        clean["use_llm"] = bool(config.get("use_llm", True))
    return clean


async def create_rule(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    kind: str,
    schedule: dict[str, Any],
    timezone: str,
    config: dict[str, Any] | None = None,
    enabled: bool = True,
    now: datetime | None = None,
) -> m.AutomationRule:
    count = (
        await session.execute(
            select(func.count()).select_from(m.AutomationRule).where(m.AutomationRule.user_id == user_id)
        )
    ).scalar_one()
    if count >= MAX_RULES_PER_USER:
        raise ValidationFailedError("Automation limit reached")
    zone(timezone)
    parsed = parse_schedule(schedule)
    now = now or utcnow()
    next_run = next_run_after(parsed, timezone, now)
    if next_run is None:
        raise ValidationFailedError("That time is already in the past", code="schedule_in_past")
    rule = m.AutomationRule(
        user_id=user_id,
        name=name.strip()[:120] or kind.replace("_", " ").title(),
        kind=kind,
        config=validate_config(kind, config or {}),
        schedule=parsed.model_dump(mode="json"),
        timezone=timezone,
        enabled=enabled,
        next_run_at=next_run if enabled else None,
    )
    session.add(rule)
    await session.flush()
    return rule


async def update_rule(
    session: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID, changes: dict[str, Any]
) -> m.AutomationRule:
    rule = await repo.get_owned(session, m.AutomationRule, user_id, rule_id, label="Automation")
    if changes.get("name") is not None:
        rule.name = str(changes["name"]).strip()[:120]
    if changes.get("config") is not None:
        rule.config = validate_config(rule.kind, changes["config"])
    if changes.get("timezone") is not None:
        zone(changes["timezone"])
        rule.timezone = changes["timezone"]
    if changes.get("schedule") is not None:
        rule.schedule = parse_schedule(changes["schedule"]).model_dump(mode="json")
    if changes.get("enabled") is not None:
        rule.enabled = bool(changes["enabled"])
    if any(changes.get(k) is not None for k in ("schedule", "timezone", "enabled")):
        rule.pending_occurrence_at = None
        rule.next_run_at = (
            next_run_after(parse_schedule(rule.schedule), rule.timezone, utcnow()) if rule.enabled else None
        )
        if rule.enabled and rule.next_run_at is None:
            raise ValidationFailedError("That schedule has no future runs", code="schedule_in_past")
    await session.flush()
    return rule
