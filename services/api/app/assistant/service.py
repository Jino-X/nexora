"""Turn orchestration shared by text, voice and automations."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.assistant.graph import build_graph
from app.assistant.prompts import conversation_title
from app.assistant.runs import Run
from app.assistant.state import TurnContext
from app.assistant.tools import Location
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.database import models as m
from app.database import repositories as repo
from app.database.session import session_scope
from app.llm.base import LLMError

if TYPE_CHECKING:
    from app.services import Services

logger = logging.getLogger("nexora.assistant")

MAX_INPUT_CHARS = 8000


@dataclass
class TurnRequest:
    user_id: uuid.UUID
    text: str
    channel: str = "text"
    conversation_id: uuid.UUID | None = None
    location: Location | None = None
    language: str | None = None
    regenerate: bool = False


@dataclass
class PreparedTurn:
    conversation_id: uuid.UUID
    text: str
    user_message_id: uuid.UUID | None
    created_conversation: bool


async def prepare_turn(services: Services, req: TurnRequest) -> PreparedTurn:
    """Validates ownership, creates the conversation if needed and stores the user message."""
    text = req.text.strip()
    if len(text) > MAX_INPUT_CHARS:
        raise ValidationFailedError(f"Message too long (max {MAX_INPUT_CHARS} characters)")
    async with session_scope(services.sessionmaker) as s:
        created = False
        if req.conversation_id:
            conv = await repo.get_owned(s, m.Conversation, req.user_id, req.conversation_id, label="Conversation")
        else:
            if req.regenerate:
                raise ValidationFailedError("regenerate requires a conversation_id")
            conv = await repo.create_conversation(s, req.user_id, title=conversation_title(text), channel=req.channel)
            created = True
        if req.regenerate:
            last_user = (
                await s.execute(
                    select(m.Message)
                    .where(
                        m.Message.conversation_id == conv.id, m.Message.user_id == req.user_id, m.Message.role == "user"
                    )
                    .order_by(m.Message.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_user is None:
                raise NotFoundError("Nothing to retry in this conversation")
            return PreparedTurn(conv.id, last_user.content, None, False)
        if not text:
            raise ValidationFailedError("Message is empty")
        if conv.title == "New conversation":
            conv.title = conversation_title(text)
        msg = await repo.add_message(s, conv, role="user", content=text, channel=req.channel)
        return PreparedTurn(conv.id, text, msg.id, created)


async def build_turn_context(
    services: Services, req: TurnRequest, conversation_id: uuid.UUID, run_id: str
) -> TurnContext:
    async with session_scope(services.sessionmaker) as s:
        profile = await s.get(m.Profile, req.user_id)
        prefs = await repo.get_preferences(s, req.user_id)
        pref_dict = {c.name: getattr(prefs, c.name) for c in m.UserPreferences.__table__.columns}
    language = req.language or prefs.preferred_language
    location = req.location if prefs.share_location else None
    return TurnContext(
        services=services,
        user_id=req.user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        channel=req.channel,
        timezone=(profile.timezone if profile else "UTC") or "UTC",
        language=language,
        display_name=profile.display_name if profile else None,
        llm=services.llm.chain(prefs.llm_mode),
        preferences=pref_dict,
        location=location,
    )


async def execute_turn(services: Services, req: TurnRequest, prepared: PreparedTurn, run: Run) -> dict[str, Any]:
    rt = await build_turn_context(services, req, prepared.conversation_id, run.id)
    await run.emit(
        "run_started",
        {
            "run_id": run.id,
            "conversation_id": str(prepared.conversation_id),
            "user_message_id": str(prepared.user_message_id) if prepared.user_message_id else None,
            "created_conversation": prepared.created_conversation,
            "channel": req.channel,
        },
    )
    final: dict[str, Any] = {}
    try:
        async for mode, chunk in build_graph().astream(
            {"user_text": prepared.text}, context=rt, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                data = dict(chunk)
                await run.emit(data.pop("type"), data)
            else:
                final = chunk
    except asyncio.CancelledError:
        await _persist_partial(services, rt, "cancelled", None)
        raise
    except LLMError as exc:
        logger.warning("llm failure: %s", exc)
        await _persist_partial(services, rt, "error", str(exc))
        await run.emit(
            "error",
            {"code": "llm_error", "message": "The language model failed to respond. Please retry.", "retryable": True},
        )
        return {}
    llm = final.get("llm", {})
    result = {
        "message_id": final.get("message_id"),
        "conversation_id": str(prepared.conversation_id),
        "content": final.get("final_text", ""),
        "provider": llm.get("provider"),
        "model": llm.get("model"),
        "offline": bool(llm.get("offline")),
        "approvals": final.get("approvals", []),
        "cards": final.get("cards", []),
        "usage": rt.usage,
    }
    await run.emit("message_end", result)
    return result


async def _persist_partial(services: Services, rt: TurnContext, status: str, error: str | None) -> None:
    text = "".join(rt.visible).strip()
    try:
        async with session_scope(services.sessionmaker) as s:
            conv = await repo.get_owned(s, m.Conversation, rt.user_id, rt.conversation_id)
            await repo.add_message(
                s,
                conv,
                role="assistant",
                content=text,
                status=status,
                run_id=rt.run_id,
                channel=rt.channel,
                meta={"error": error} if error else {},
            )
    except Exception:
        logger.exception("failed to persist partial assistant message")
