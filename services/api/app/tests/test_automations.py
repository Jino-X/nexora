"""Automation engine: schedule maths, durable claiming, idempotency, retries, notifications."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.automations import scheduler as scheduler_module
from app.automations.schedule import next_run_after, parse_schedule, upcoming
from app.automations.scheduler import AutomationScheduler
from app.core.exceptions import ValidationFailedError
from app.database import models as m
from app.database.base import utcnow
from app.database.session import session_scope
from app.tests.conftest import user_id

ALICE = user_id("alice@example.com")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_daily_in_ist():
    s = parse_schedule({"type": "daily", "time": "07:30"})
    # 2026-11-14 01:00 UTC = 06:30 IST -> today 07:30 IST = 02:00 UTC
    assert next_run_after(s, "Asia/Kolkata", utc(2026, 11, 14, 1, 0)) == utc(2026, 11, 14, 2, 0)
    assert next_run_after(s, "Asia/Kolkata", utc(2026, 11, 14, 2, 0)) == utc(2026, 11, 15, 2, 0)


def test_weekly_weekdays_only():
    s = parse_schedule({"type": "weekly", "time": "09:00", "days": [0, 1, 2, 3, 4]})
    runs = upcoming(s, "UTC", utc(2026, 11, 13, 10, 0), 3)  # Friday after 9am
    assert [r.weekday() for r in runs] == [0, 1, 2]


def test_dst_transition_new_york():
    s = parse_schedule({"type": "daily", "time": "08:00"})
    # DST ends 2026-11-01 02:00 local. Same wall-clock time, different UTC offsets.
    before = next_run_after(s, "America/New_York", utc(2026, 10, 30, 13, 0))
    after = next_run_after(s, "America/New_York", utc(2026, 10, 31, 13, 0))
    assert before == utc(2026, 10, 31, 12, 0)  # 08:00 EDT (UTC-4)
    assert after == utc(2026, 11, 1, 13, 0)  # 08:00 EST (UTC-5)


def test_once_and_interval():
    once = parse_schedule({"type": "once", "at": "2026-11-15T09:00"})
    assert next_run_after(once, "Asia/Kolkata", utc(2026, 11, 14)) == utc(2026, 11, 15, 3, 30)
    assert next_run_after(once, "Asia/Kolkata", utc(2026, 11, 16)) is None
    interval = parse_schedule({"type": "interval", "minutes": 30})
    assert next_run_after(interval, "UTC", utc(2026, 1, 1)) == utc(2026, 1, 1, 0, 30)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "daily", "time": "25:00"},
        {"type": "weekly", "time": "09:00", "days": [7]},
        {"type": "interval", "minutes": 1},
        {"type": "cron", "expr": "* * * * *"},
    ],
)
def test_invalid_schedules(bad):
    with pytest.raises(ValidationFailedError):
        parse_schedule(bad)


async def _make_rule(client, headers, **body):
    payload = {
        "kind": "reminder",
        "name": "Call client",
        "schedule": {"type": "daily", "time": "09:00"},
        "timezone": "UTC",
        "config": {"message": "Call the client"},
        **body,
    }
    res = await client.post("/api/v1/automations", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _force_due(services, rule_id):
    async with session_scope(services.sessionmaker) as s:
        rule = await s.get(m.AutomationRule, __import__("uuid").UUID(rule_id))
        rule.next_run_at = utcnow() - timedelta(seconds=5)


async def test_reminder_runs_and_notifies(client, alice, services):
    rule = await _make_rule(client, alice)
    await _force_due(services, rule["id"])
    assert await AutomationScheduler(services).tick() == 1
    notes = (await client.get("/api/v1/notifications", headers=alice)).json()["items"]
    assert notes[0]["kind"] == "reminder" and notes[0]["body"] == "Call the client"
    runs = (await client.get(f"/api/v1/automations/{rule['id']}/runs", headers=alice)).json()["items"]
    assert runs[0]["status"] == "succeeded"
    after = (await client.get(f"/api/v1/automations/{rule['id']}", headers=alice)).json()
    assert after["last_status"] == "succeeded"
    assert datetime.fromisoformat(after["next_run_at"]) > utcnow()


async def test_concurrent_workers_execute_once(client, alice, services):
    rule = await _make_rule(client, alice)
    await _force_due(services, rule["id"])
    workers = [AutomationScheduler(services) for _ in range(3)]
    await asyncio.gather(*(w.tick() for w in workers))
    async with session_scope(services.sessionmaker) as s:
        assert (await s.execute(select(func.count()).select_from(m.TaskRun))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(m.Notification))).scalar_one() == 1


async def test_duplicate_occurrence_is_idempotent(client, alice, services):
    rule = await _make_rule(client, alice)
    await _force_due(services, rule["id"])
    async with session_scope(services.sessionmaker) as s:
        r = await s.get(m.AutomationRule, __import__("uuid").UUID(rule["id"]))
        occurrence = r.next_run_at
    worker = AutomationScheduler(services)
    await worker.tick()
    # Simulate a crash that left next_run_at on the already-executed occurrence.
    async with session_scope(services.sessionmaker) as s:
        r = await s.get(m.AutomationRule, __import__("uuid").UUID(rule["id"]))
        r.next_run_at = occurrence
    await worker.tick()
    async with session_scope(services.sessionmaker) as s:
        assert (await s.execute(select(func.count()).select_from(m.TaskRun))).scalar_one() == 1
        assert (await s.execute(select(func.count()).select_from(m.Notification))).scalar_one() == 1


async def test_retry_with_backoff_then_fail(client, alice, services, monkeypatch):
    rule = await _make_rule(client, alice)
    calls = {"n": 0}

    async def failing(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("provider down")

    monkeypatch.setattr(scheduler_module, "run_automation", failing)
    worker = AutomationScheduler(services)
    for _ in range(3):  # 1 attempt + 2 retries (max_retries=2)
        await _force_due(services, rule["id"])
        await worker.tick()
    async with session_scope(services.sessionmaker) as s:
        runs = (await s.execute(select(m.TaskRun))).scalars().all()
        assert len(runs) == 1 and runs[0].attempt == 3 and runs[0].status == "failed"
        r = await s.get(m.AutomationRule, __import__("uuid").UUID(rule["id"]))
        assert r.pending_occurrence_at is None and r.consecutive_failures == 3
        notes = (await s.execute(select(m.Notification))).scalars().all()
        assert any("failed" in n.title for n in notes)
    assert calls["n"] == 3


async def test_expired_lease_is_reclaimed(client, alice, services):
    rule = await _make_rule(client, alice)
    await _force_due(services, rule["id"])
    worker = AutomationScheduler(services)
    token = await worker.claim(__import__("uuid").UUID(rule["id"]), utcnow())
    assert token
    assert await worker.claim(__import__("uuid").UUID(rule["id"]), utcnow()) is None  # still leased
    later = utcnow() + timedelta(seconds=services.settings.automation_timeout_seconds + 120)
    assert await worker.claim(__import__("uuid").UUID(rule["id"]), later)  # crashed worker's lease expired


async def test_once_reminder_via_assistant_offline(client, alice):
    res = await client.post(
        "/api/v1/assistant/runs", json={"message": "remind me to call my client tomorrow at 10am"}, headers=alice
    )
    assert "Reminder set for" in res.text
    rules = (await client.get("/api/v1/automations", headers=alice)).json()
    assert rules[0]["kind"] == "reminder" and rules[0]["schedule"]["type"] == "once"


async def test_morning_briefing_template(client, alice, services):
    await client.patch(
        "/api/v1/me/preferences",
        json={"home_latitude": 13.08, "home_longitude": 80.27, "home_label": "Chennai"},
        headers=alice,
    )
    rule = await _make_rule(client, alice, kind="morning_briefing", name="Morning", config={})
    await _force_due(services, rule["id"])
    await AutomationScheduler(services).tick()
    note = (await client.get("/api/v1/notifications", headers=alice)).json()["items"][0]
    assert "Chennai" in note["body"] and "Headlines" in note["body"]
    dash = (await client.get("/api/v1/dashboard", headers=alice)).json()
    assert dash["latest_briefing"]["sections"]["weather"]["location"] == "Chennai"


async def test_past_once_schedule_rejected(client, alice):
    res = await client.post(
        "/api/v1/automations",
        json={
            "kind": "reminder",
            "schedule": {"type": "once", "at": "2020-01-01T09:00"},
            "timezone": "UTC",
            "config": {"message": "x"},
        },
        headers=alice,
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "schedule_in_past"


async def test_preview(client, alice):
    res = await client.post(
        "/api/v1/automations/preview",
        json={"schedule": {"type": "daily", "time": "07:00"}, "timezone": "Asia/Kolkata"},
        headers=alice,
    )
    body = res.json()
    assert body["description"] == "daily at 07:00" and len(body["next_runs"]) == 5
