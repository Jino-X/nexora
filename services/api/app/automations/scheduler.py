"""Durable automation scheduler.

* Schedules live in the database (`automation_rules.next_run_at`). There are no in-memory timers.
* Workers claim due rules with a conditional UPDATE (lease with token + expiry), so several workers
  (or API replicas) can run without double execution. A crashed worker's lease expires and the
  rule is picked up again.
* Each occurrence has one `task_runs` row keyed by `automation:<rule>:<scheduled_for>` (UNIQUE),
  which makes execution idempotent. Retries reuse that row and increment `attempt`.
* Retries use exponential backoff up to `max_retries`, then the failure is recorded and notified.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.automations.executor import run_automation
from app.automations.schedule import next_run_after, parse_schedule
from app.core.exceptions import AppError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.database.session import session_scope

if TYPE_CHECKING:
    from app.services import Services

logger = logging.getLogger("nexora.scheduler")


def backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(30 * (2 ** max(0, attempt - 1)), 1800))


class AutomationScheduler:
    def __init__(self, services: Services) -> None:
        self.services = services
        self.settings = services.settings
        self.worker_id = uuid.uuid4().hex[:8]
        self._ticks = 0

    async def run_forever(self, stop: asyncio.Event) -> None:
        logger.info("automation scheduler started (worker %s)", self.worker_id)
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.scheduler_poll_seconds)
            except TimeoutError:
                pass

    async def tick(self, now: datetime | None = None) -> int:
        now = now or utcnow()
        self._ticks += 1
        if self._ticks % 20 == 1:
            await self.housekeeping(now)
        async with session_scope(self.services.sessionmaker) as s:
            due = (
                (
                    await s.execute(
                        select(m.AutomationRule.id)
                        .where(
                            m.AutomationRule.enabled.is_(True),
                            m.AutomationRule.next_run_at.is_not(None),
                            m.AutomationRule.next_run_at <= now,
                            or_(m.AutomationRule.locked_until.is_(None), m.AutomationRule.locked_until < now),
                        )
                        .order_by(m.AutomationRule.next_run_at)
                        .limit(self.settings.scheduler_batch_size)
                    )
                )
                .scalars()
                .all()
            )
        processed = 0
        for rule_id in due:
            token = await self.claim(rule_id, now)
            if token:
                await self.process(rule_id, token, now)
                processed += 1
        return processed

    async def claim(self, rule_id: uuid.UUID, now: datetime) -> str | None:
        token = f"{self.worker_id}:{uuid.uuid4().hex[:12]}"
        lease = now + timedelta(seconds=self.settings.automation_timeout_seconds + 60)
        async with session_scope(self.services.sessionmaker) as s:
            result = await s.execute(
                update(m.AutomationRule)
                .where(
                    m.AutomationRule.id == rule_id,
                    m.AutomationRule.enabled.is_(True),
                    m.AutomationRule.next_run_at <= now,
                    or_(m.AutomationRule.locked_until.is_(None), m.AutomationRule.locked_until < now),
                )
                .values(locked_until=lease, lock_token=token)
                .execution_options(synchronize_session=False)
            )
            return token if (result.rowcount or 0) == 1 else None  # type: ignore[attr-defined]

    async def process(self, rule_id: uuid.UUID, token: str, now: datetime) -> None:
        async with session_scope(self.services.sessionmaker) as s:
            rule = await s.get(m.AutomationRule, rule_id)
            if rule is None or rule.lock_token != token:
                return
            user_id = rule.user_id
            scheduled_for = rule.pending_occurrence_at or rule.next_run_at or now
            key = f"automation:{rule.id}:{scheduled_for.isoformat()}"
            run = (await s.execute(select(m.TaskRun).where(m.TaskRun.idempotency_key == key))).scalar_one_or_none()
            if run is not None and run.status == "succeeded":
                self._advance(rule, scheduled_for, now, success=True, attempt=run.attempt)
                self._release(rule)
                return
            if run is None:
                run = m.TaskRun(
                    user_id=user_id,
                    automation_id=rule.id,
                    kind="automation",
                    title=rule.name,
                    status="running",
                    idempotency_key=key,
                    scheduled_for=scheduled_for,
                    started_at=now,
                    attempt=1,
                )
                s.add(run)
                try:
                    await s.flush()
                except IntegrityError:
                    await s.rollback()
                    return  # another worker created this occurrence concurrently
            else:
                run.attempt += 1
                run.status = "running"
                run.started_at = now
            run_id, attempt = run.id, run.attempt

        error: str | None = None
        result: dict[str, object] = {}
        try:
            result = await asyncio.wait_for(
                run_automation(self.services, rule_id, user_id), timeout=self.settings.automation_timeout_seconds
            )
        except TimeoutError:
            error = "Timed out"
        except AppError as exc:
            error = exc.message
        except Exception as exc:
            logger.exception("automation %s failed", rule_id)
            error = f"{type(exc).__name__}"

        finished = utcnow()
        async with session_scope(self.services.sessionmaker) as s:
            rule = await s.get(m.AutomationRule, rule_id)
            run = await s.get(m.TaskRun, run_id)
            if rule is None or run is None:
                return
            run.finished_at = finished
            if error is None:
                run.status, run.result, run.error = "succeeded", _jsonable(result), None
                self._advance(rule, scheduled_for, finished, success=True, attempt=attempt)
            else:
                run.error = error
                retry = attempt <= rule.max_retries
                run.status = "retrying" if retry else "failed"
                self._advance(rule, scheduled_for, finished, success=False, attempt=attempt, retry=retry)
                if not retry:
                    await repo.notify(
                        s,
                        rule.user_id,
                        kind="automation",
                        title=f"'{rule.name}' failed",
                        body=error,
                        data={"automation_id": str(rule.id), "task_run_id": str(run.id)},
                    )
            s.add(
                m.ExecutionLog(
                    user_id=rule.user_id,
                    run_id=str(run.id),
                    event_type="automation",
                    name=rule.kind,
                    status="ok" if error is None else "error",
                    duration_ms=int((finished - now).total_seconds() * 1000),
                    error=error,
                    details={"attempt": attempt, "automation_id": str(rule.id)},
                )
            )
            self._release(rule, token)

    def _advance(
        self,
        rule: m.AutomationRule,
        scheduled_for: datetime,
        now: datetime,
        *,
        success: bool,
        attempt: int,
        retry: bool = False,
    ) -> None:
        rule.last_run_at = now
        if success:
            rule.last_status = "succeeded"
            rule.consecutive_failures = 0
        else:
            rule.last_status = "failed"
            rule.consecutive_failures += 1
        if retry:
            rule.pending_occurrence_at = scheduled_for
            rule.next_run_at = now + backoff(attempt)
            return
        rule.pending_occurrence_at = None
        # Skip occurrences missed while the worker was down (no catch-up storms).
        rule.next_run_at = next_run_after(parse_schedule(rule.schedule), rule.timezone, max(now, scheduled_for))

    @staticmethod
    def _release(rule: m.AutomationRule, token: str | None = None) -> None:
        if token is None or rule.lock_token == token:
            rule.locked_until = None
            rule.lock_token = None

    async def housekeeping(self, now: datetime) -> None:
        async with session_scope(self.services.sessionmaker) as s:
            await repo.expire_stale_approvals(s, now)
            await repo.purge_expired_memories(s, now)
            await s.execute(
                update(m.VoiceSession)
                .where(
                    m.VoiceSession.status.in_(("created", "active")),
                    m.VoiceSession.expires_at < now - timedelta(seconds=self.settings.voice_max_session_seconds),
                )
                .values(status="expired", ended_at=now, end_reason="expired")
            )
            await s.execute(delete(m.OAuthState).where(m.OAuthState.expires_at < now))
            prefs = (
                (
                    await s.execute(
                        select(m.UserPreferences).where(m.UserPreferences.conversation_retention_days.is_not(None))
                    )
                )
                .scalars()
                .all()
            )
            for p in prefs:
                cutoff = now - timedelta(days=int(p.conversation_retention_days or 0))
                await s.execute(
                    delete(m.Conversation).where(
                        and_(m.Conversation.user_id == p.user_id, m.Conversation.last_message_at < cutoff)
                    )
                )


def _jsonable(value: object) -> dict[str, object]:
    import json

    return json.loads(json.dumps(value, default=str)) if isinstance(value, dict) else {"value": str(value)}
