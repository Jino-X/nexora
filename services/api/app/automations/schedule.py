"""Timezone-aware schedule definitions and next-run computation.

Schedules are stored as JSON on `automation_rules.schedule`, and times are local to the rule's
IANA timezone:
    {"type": "once", "at": "2026-11-15T09:00"}
    {"type": "daily", "time": "07:30"}
    {"type": "weekly", "time": "07:30", "days": [0, 1, 2, 3, 4]}   # Monday = 0
    {"type": "interval", "minutes": 60}
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from app.core.exceptions import ValidationFailedError

HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class OnceSchedule(BaseModel):
    type: Literal["once"]
    at: datetime  # local wall time (naive) or an explicit offset


class DailySchedule(BaseModel):
    type: Literal["daily"]
    time: HHMM


class WeeklySchedule(BaseModel):
    type: Literal["weekly"]
    time: HHMM
    days: list[int] = Field(min_length=1, max_length=7)

    @field_validator("days")
    @classmethod
    def _days(cls, value: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in value):
            raise ValueError("days must be 0 (Monday) .. 6 (Sunday)")
        return sorted(set(value))


class IntervalSchedule(BaseModel):
    type: Literal["interval"]
    minutes: int = Field(ge=5, le=60 * 24 * 7)


Schedule = Annotated[OnceSchedule | DailySchedule | WeeklySchedule | IntervalSchedule, Field(discriminator="type")]
_adapter: TypeAdapter[Schedule] = TypeAdapter(Schedule)


def parse_schedule(raw: dict[str, object]) -> Schedule:
    try:
        return _adapter.validate_python(raw)
    except ValueError as exc:
        raise ValidationFailedError("Invalid schedule", details=str(exc)) from exc


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailedError(f"Unknown timezone '{name}'") from exc


def _local(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(hour, minute), tzinfo=tz)


def next_run_after(schedule: Schedule, tz_name: str, after: datetime) -> datetime | None:
    """First occurrence strictly after `after` (UTC-aware), returned in UTC. None when exhausted."""
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")
    tz = zone(tz_name)
    if isinstance(schedule, OnceSchedule):
        at = schedule.at if schedule.at.tzinfo else schedule.at.replace(tzinfo=tz)
        at_utc = at.astimezone(UTC)
        return at_utc if at_utc > after else None
    if isinstance(schedule, IntervalSchedule):
        return (after + timedelta(minutes=schedule.minutes)).astimezone(UTC)
    local_after = after.astimezone(tz)
    allowed = set(range(7)) if isinstance(schedule, DailySchedule) else set(schedule.days)
    for offset in range(0, 9):
        day = local_after.date() + timedelta(days=offset)
        if day.weekday() not in allowed:
            continue
        candidate = _local(day, schedule.time, tz).astimezone(UTC)
        if candidate > after:
            return candidate
    return None


def upcoming(schedule: Schedule, tz_name: str, after: datetime, count: int = 5) -> list[datetime]:
    out: list[datetime] = []
    cursor = after
    for _ in range(count):
        nxt = next_run_after(schedule, tz_name, cursor)
        if nxt is None:
            break
        out.append(nxt)
        cursor = nxt
    return out


def describe(schedule: Schedule) -> str:
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if isinstance(schedule, OnceSchedule):
        return f"once at {schedule.at:%Y-%m-%d %H:%M}"
    if isinstance(schedule, DailySchedule):
        return f"daily at {schedule.time}"
    if isinstance(schedule, WeeklySchedule):
        return f"every {', '.join(names[d] for d in schedule.days)} at {schedule.time}"
    return f"every {schedule.minutes} minutes"
