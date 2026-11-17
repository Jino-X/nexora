"""Graph state and per-turn runtime context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

from app.assistant.tools import Location
from app.llm.base import ChatMessage, ToolCall

if TYPE_CHECKING:
    from app.database import models as m
    from app.llm.factory import FallbackLLM
    from app.services import Services


class TurnState(TypedDict, total=False):
    user_text: str
    history: list[ChatMessage]
    system_prompt: str
    memories: list[dict[str, Any]]
    working: list[ChatMessage]  # assistant tool-call messages and tool results of this turn
    pending: list[ToolCall]
    authorized: list[dict[str, Any]]
    steps: int
    final_text: str
    tool_trace: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    llm: dict[str, Any]
    message_id: str


@dataclass
class TurnContext:
    """Dependencies and identity for one assistant turn (LangGraph runtime context)."""

    services: Services
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    run_id: str
    channel: str  # text | voice | automation
    timezone: str
    language: str
    display_name: str | None
    llm: FallbackLLM
    preferences: dict[str, Any]
    location: Location | None = None
    permissions: dict[str, m.ToolPermission] = field(default_factory=dict)
    connected: set[str] = field(default_factory=set)
    visible: list[str] = field(default_factory=list)  # every token streamed to the user
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
