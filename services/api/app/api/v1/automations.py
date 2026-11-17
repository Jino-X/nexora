from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, ServicesDep
from app.automations.schedule import describe, parse_schedule, upcoming, zone
from app.automations.service import create_rule, update_rule
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.schemas.common import OkResponse, Page
from app.schemas.resources import (
    AutomationCreate,
    AutomationOut,
    AutomationUpdate,
    SchedulePreviewIn,
    SchedulePreviewOut,
    TaskRunOut,
)

router = APIRouter(prefix="/automations", tags=["automations"])


def _out(rule: m.AutomationRule) -> AutomationOut:
    out = AutomationOut.model_validate(rule)
    out.schedule_description = describe(parse_schedule(rule.schedule))
    return out


@router.get("", response_model=list[AutomationOut])
async def list_rules(user: CurrentUser, db: DB, kind: str | None = Query(None, max_length=32)) -> list[AutomationOut]:
    stmt = select(m.AutomationRule).where(m.AutomationRule.user_id == user.id)
    if kind:
        stmt = stmt.where(m.AutomationRule.kind == kind)
    rows = (await db.execute(stmt.order_by(m.AutomationRule.created_at.desc()))).scalars().all()
    return [_out(r) for r in rows]


@router.post("", response_model=AutomationOut, status_code=201)
async def create(body: AutomationCreate, user: CurrentUser, db: DB) -> AutomationOut:
    profile = await db.get(m.Profile, user.id)
    tz = body.timezone or (profile.timezone if profile else "UTC")
    rule = await create_rule(
        db,
        user.id,
        name=body.name,
        kind=body.kind,
        schedule=body.schedule,
        timezone=tz,
        config=body.config,
        enabled=body.enabled,
    )
    return _out(rule)


@router.post("/preview", response_model=SchedulePreviewOut)
async def preview(body: SchedulePreviewIn, user: CurrentUser) -> SchedulePreviewOut:
    zone(body.timezone)
    schedule = parse_schedule(body.schedule)
    return SchedulePreviewOut(description=describe(schedule), next_runs=upcoming(schedule, body.timezone, utcnow()))


@router.get("/{rule_id}", response_model=AutomationOut)
async def get_rule(rule_id: uuid.UUID, user: CurrentUser, db: DB) -> AutomationOut:
    return _out(await repo.get_owned(db, m.AutomationRule, user.id, rule_id, label="Automation"))


@router.patch("/{rule_id}", response_model=AutomationOut)
async def patch_rule(rule_id: uuid.UUID, body: AutomationUpdate, user: CurrentUser, db: DB) -> AutomationOut:
    return _out(await update_rule(db, user.id, rule_id, body.model_dump(exclude_none=True)))


@router.delete("/{rule_id}", response_model=OkResponse)
async def delete_rule(rule_id: uuid.UUID, user: CurrentUser, db: DB) -> OkResponse:
    await db.delete(await repo.get_owned(db, m.AutomationRule, user.id, rule_id, label="Automation"))
    return OkResponse()


@router.post("/{rule_id}/run", response_model=AutomationOut)
async def run_now(rule_id: uuid.UUID, user: CurrentUser, db: DB, services: ServicesDep) -> AutomationOut:
    """Queue an immediate run. The worker picks it up on its next tick; the regular schedule resumes after."""
    rule = await repo.get_owned(db, m.AutomationRule, user.id, rule_id, label="Automation")
    services.rate_limiter.check(f"automation-run:{user.id}", 10)
    rule.enabled = True
    rule.pending_occurrence_at = None
    rule.next_run_at = utcnow()
    await db.flush()
    return _out(rule)


@router.get("/{rule_id}/runs", response_model=Page[TaskRunOut])
async def rule_runs(
    rule_id: uuid.UUID, user: CurrentUser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Page[TaskRunOut]:
    await repo.get_owned(db, m.AutomationRule, user.id, rule_id, label="Automation")
    stmt = (
        select(m.TaskRun)
        .where(m.TaskRun.user_id == user.id, m.TaskRun.automation_id == rule_id)
        .order_by(m.TaskRun.created_at.desc())
    )
    rows, more = await repo.paginate(db, stmt, limit, offset)
    return Page.of([TaskRunOut.model_validate(r) for r in rows], more, offset, limit)
