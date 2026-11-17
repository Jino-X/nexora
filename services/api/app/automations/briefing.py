"""Daily briefing composition: weather, headlines, unread email count and today's reminders.
Each section degrades on its own: a missing integration or a failing provider skips that section
and never fails the whole briefing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.llm.base import ChatMessage, LLMError

if TYPE_CHECKING:
    from app.services import Services

logger = logging.getLogger("nexora.briefing")


async def build_briefing(
    services: Services, session: AsyncSession, user_id: uuid.UUID, *, use_llm: bool = True, news_limit: int = 5
) -> dict[str, Any]:
    profile = await session.get(m.Profile, user_id)
    prefs = await repo.get_preferences(session, user_id)
    tz_name = profile.timezone if profile else "UTC"
    now_local = datetime.now(ZoneInfo(tz_name))
    sections: dict[str, Any] = {}
    issues: list[str] = []

    if prefs.home_latitude is not None and prefs.home_longitude is not None:
        try:
            report = await services.weather.forecast(prefs.home_latitude, prefs.home_longitude, days=2)
            today = report.daily[0] if report.daily else None
            sections["weather"] = {
                "location": prefs.home_label,
                "now_c": report.current.temperature_c,
                "conditions": report.current.description,
                "min_c": today.temperature_min_c if today else None,
                "max_c": today.temperature_max_c if today else None,
                "rain_chance": today.precipitation_probability_max if today else None,
            }
        except AppError as exc:
            issues.append(f"weather: {exc.message}")
    else:
        issues.append("weather: set a home location in Settings")

    try:
        items = await services.news.headlines(prefs.news_categories or None, limit=news_limit)
        sections["news"] = [{"title": i.title, "source": i.source, "link": i.link} for i in items]
    except AppError as exc:
        issues.append(f"news: {exc.message}")

    if "gmail" in await repo.connected_providers(session, user_id):
        try:
            client = await services.gmail.client_for(session, user_id)
            unread = await client.list_messages("is:unread in:inbox", 10)
            sections["email"] = {
                "unread_count": len(unread),
                "top": [{"from": e.from_, "subject": e.subject} for e in unread[:5]],
            }
        except AppError as exc:
            issues.append(f"email: {exc.message}")

    end_of_day = (now_local.replace(hour=23, minute=59, second=59)).astimezone(ZoneInfo("UTC"))
    reminders = (
        (
            await session.execute(
                select(m.AutomationRule)
                .where(
                    m.AutomationRule.user_id == user_id,
                    m.AutomationRule.kind == "reminder",
                    m.AutomationRule.enabled.is_(True),
                    m.AutomationRule.next_run_at.is_not(None),
                    m.AutomationRule.next_run_at <= end_of_day,
                    m.AutomationRule.next_run_at >= utcnow() - timedelta(minutes=1),
                )
                .order_by(m.AutomationRule.next_run_at)
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    if reminders:
        sections["reminders"] = [
            {
                "message": r.config.get("message"),
                "at": r.next_run_at.astimezone(ZoneInfo(tz_name)).strftime("%H:%M") if r.next_run_at else None,
            }
            for r in reminders
        ]

    greeting = "Good morning" if now_local.hour < 12 else "Good afternoon" if now_local.hour < 17 else "Good evening"
    name = (profile.display_name if profile else None) or "there"
    text = template_briefing(greeting, name, sections)
    mode = "template"
    if use_llm:
        llm = services.llm.chain(prefs.llm_mode)
        if not llm.providers[0].offline:
            try:
                res = await llm.chat(
                    [
                        ChatMessage(
                            "system",
                            "You write short, warm daily briefings for one person. Use only the "
                            "facts provided. Mention news sources by name. 120 words max. No markdown.",
                        ),
                        ChatMessage("user", f"{greeting}, {name}. Facts (JSON): {sections}"),
                    ],
                    temperature=0.3,
                    max_tokens=400,
                )
                if res.content and not res.offline:
                    text, mode = res.content, f"llm:{res.provider}"
            except LLMError as exc:
                logger.warning("briefing llm failed: %s", exc)
    return {
        "generated_at": utcnow().isoformat(),
        "timezone": tz_name,
        "text": text,
        "mode": mode,
        "sections": sections,
        "issues": issues,
    }


def template_briefing(greeting: str, name: str, sections: dict[str, Any]) -> str:
    parts = [f"{greeting}, {name}."]
    if w := sections.get("weather"):
        parts.append(
            f"It's {w['now_c']:.0f}°C and {str(w['conditions']).lower()}"
            + (f" in {w['location']}" if w.get("location") else "")
            + (f", with a {w['rain_chance']:.0f}% chance of rain today." if w.get("rain_chance") is not None else ".")
        )
    if e := sections.get("email"):
        parts.append(f"You have {e['unread_count']} unread email(s).")
    if r := sections.get("reminders"):
        parts.append("Today: " + "; ".join(f"{x['message']} at {x['at']}" for x in r) + ".")
    if n := sections.get("news"):
        parts.append("Headlines: " + "; ".join(f"{x['title']} ({x['source']})" for x in n[:3]) + ".")
    return " ".join(parts)
