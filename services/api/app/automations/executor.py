"""Executes one automation occurrence."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.runs import Run
from app.assistant.service import TurnRequest, execute_turn, prepare_turn
from app.automations.briefing import build_briefing
from app.core.exceptions import NotConfiguredError
from app.database import models as m
from app.database import repositories as repo
from app.database.session import session_scope
from app.llm.base import ChatMessage, LLMError

if TYPE_CHECKING:
    from app.services import Services


async def _summarize(services: Services, mode: str, instruction: str, facts: Any) -> tuple[str | None, str]:
    llm = services.llm.chain(mode)
    if llm.providers[0].offline:
        return None, "template"
    try:
        res = await llm.chat(
            [ChatMessage("system", instruction), ChatMessage("user", f"Facts (JSON): {facts}")],
            temperature=0.3,
            max_tokens=400,
        )
    except LLMError:
        return None, "template"
    return (res.content or None), ("template" if res.offline else f"llm:{res.provider}")


async def run_automation(services: Services, rule_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    async with session_scope(services.sessionmaker) as s:
        rule = await repo.get_owned(s, m.AutomationRule, user_id, rule_id, label="Automation")
        prefs = await repo.get_preferences(s, user_id)
        kind, config, name = rule.kind, dict(rule.config or {}), rule.name
        llm_mode = prefs.llm_mode
        news_categories = list(prefs.news_categories or [])

    if kind == "reminder":
        async with session_scope(services.sessionmaker) as s:
            await repo.notify(
                s,
                user_id,
                kind="reminder",
                title="Reminder",
                body=config.get("message", ""),
                data={"automation_id": str(rule_id)},
            )
        return {"message": config.get("message", "")}

    if kind == "morning_briefing":
        async with session_scope(services.sessionmaker) as s:
            briefing = await build_briefing(services, s, user_id, use_llm=config.get("use_llm", True))
            await repo.notify(
                s,
                user_id,
                kind="automation",
                title=name or "Your briefing",
                body=briefing["text"],
                data={"automation_id": str(rule_id), "kind": kind},
            )
        return {"briefing": briefing}

    if kind == "news_summary":
        items = await services.news.headlines(config.get("categories") or news_categories or None, limit=8)
        facts = [{"title": i.title, "source": i.source} for i in items]
        text, mode = await _summarize(
            services, llm_mode, "Summarise these headlines in under 100 words. Name sources. No markdown.", facts
        )
        text = text or ("Headlines: " + "; ".join(f"{i.title} ({i.source})" for i in items[:5]))
        async with session_scope(services.sessionmaker) as s:
            await _notify(s, user_id, name or "News summary", text, rule_id, kind)
        return {"text": text, "mode": mode, "items": [i.model_dump(mode="json") for i in items]}

    if kind == "email_summary":
        async with session_scope(services.sessionmaker) as s:
            if "gmail" not in await repo.connected_providers(s, user_id):
                raise NotConfiguredError("Gmail is not connected", code="gmail_not_connected")
            client = await services.gmail.client_for(s, user_id)
        emails = await client.list_messages("is:unread in:inbox", 15)
        facts = [{"from": e.from_, "subject": e.subject, "snippet": e.snippet} for e in emails]
        text, mode = await _summarize(
            services,
            llm_mode,
            "Summarise these unread emails in under 120 words, most important first. "
            "Never invent content. No markdown.",
            facts,
        )
        text = text or (
            f"You have {len(emails)} unread email(s)."
            + ("" if not emails else " Latest: " + "; ".join(f"{e.subject} from {e.from_}" for e in emails[:3]) + ".")
        )
        async with session_scope(services.sessionmaker) as s:
            await _notify(s, user_id, name or "Email summary", text, rule_id, kind)
        return {"text": text, "mode": mode, "count": len(emails)}

    if kind == "assistant_prompt":
        conv_id = config.get("conversation_id")
        async with session_scope(services.sessionmaker) as s:
            conv = None
            if conv_id:
                conv = await s.get(m.Conversation, uuid.UUID(conv_id))
                if conv is not None and conv.user_id != user_id:
                    conv = None
            if conv is None:
                conv = await repo.create_conversation(
                    s, user_id, title=f"Automation: {name}"[:200], channel="automation"
                )
                rule = await repo.get_owned(s, m.AutomationRule, user_id, rule_id)
                rule.config = {**rule.config, "conversation_id": str(conv.id)}
            conversation_id = conv.id
        req = TurnRequest(user_id=user_id, text=config["prompt"], channel="automation", conversation_id=conversation_id)
        prepared = await prepare_turn(services, req)
        run = Run(id=uuid.uuid4().hex, user_id=user_id, conversation_id=conversation_id, channel="automation")
        result = await execute_turn(services, req, prepared, run)
        if not result:
            raise RuntimeError("The assistant could not complete the scheduled prompt")
        async with session_scope(services.sessionmaker) as s:
            body = result["content"]
            if result.get("approvals"):
                body += " (Waiting for your approval.)"
            await repo.notify(
                s,
                user_id,
                kind="automation",
                title=name or "Scheduled task",
                body=body[:2000],
                data={"automation_id": str(rule_id), "conversation_id": str(conversation_id)},
            )
        return {
            "text": result["content"],
            "conversation_id": str(conversation_id),
            "approvals": result.get("approvals", []),
        }

    raise ValueError(f"unsupported automation kind {kind}")


async def _notify(s: AsyncSession, user_id: uuid.UUID, title: str, body: str, rule_id: uuid.UUID, kind: str) -> None:
    await repo.notify(
        s, user_id, kind="automation", title=title, body=body, data={"automation_id": str(rule_id), "kind": kind}
    )
