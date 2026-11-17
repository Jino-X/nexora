"""Typed tool registry. Tools are the *only* way the assistant can act. Each tool has a Pydantic
argument model, a risk level, an approval policy and an optional per-user integration requirement.
There is no tool for shell access, raw HTTP, SQL or code execution."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.services import Services

Risk = Literal["read", "write", "sensitive"]
ApprovalPolicy = Literal["never", "always", "configurable"]


@dataclass
class Location:
    latitude: float
    longitude: float
    label: str | None = None


@dataclass
class ToolContext:
    services: Services
    session: AsyncSession
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None
    run_id: str | None
    channel: str  # text | voice | automation | approval
    timezone: str
    location: Location | None
    preferences: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    ok: bool
    message: str = ""  # one-line human summary (also used by offline mode)
    data: Any = None  # compact JSON passed to the LLM
    card: dict[str, Any] | None = None  # rich UI card, never sent to the LLM
    error_code: str | None = None

    def for_llm(self, limit: int = 6000) -> str:
        import json

        payload: dict[str, Any] = {"ok": self.ok, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        if self.error_code:
            payload["error_code"] = self.error_code
        text = json.dumps(payload, default=str, ensure_ascii=False)
        return text if len(text) <= limit else text[: limit - 20] + '..."}'


Handler = Callable[[ToolContext, Any], Awaitable[ToolResult]]


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler
    category: str
    risk: Risk = "read"
    approval: ApprovalPolicy = "never"
    integration: str | None = None  # per-user connection required (gmail, whatsapp)
    timeout_seconds: float = 25.0
    summarize: Callable[[Any], str] | None = None  # human summary shown in approval prompts
    channels: tuple[str, ...] = ("text", "voice", "automation", "approval")

    def json_schema(self) -> dict[str, Any]:
        schema = copy.deepcopy(self.args_model.model_json_schema())
        _strip_titles(schema)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": schema},
        }

    def approval_summary(self, args: BaseModel) -> str:
        if self.summarize:
            return self.summarize(args)
        return f"{self.name}({args.model_dump_json(exclude_none=True)})"


def _strip_titles(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("title", None)
        for value in node.values():
            _strip_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_titles(value)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools)


def tool(registry: ToolRegistry, **kwargs: Any) -> Callable[[Handler], Handler]:
    """Decorator: @tool(registry, name=..., description=..., args_model=..., category=...)."""

    def wrap(fn: Handler) -> Handler:
        registry.register(ToolSpec(handler=fn, **kwargs))
        return fn

    return wrap


def build_registry() -> ToolRegistry:
    from app.agents import (
        automation_agent,
        email_agent,
        location_agent,
        media_agent,
        memory_agent,
        messaging_agent,
        news_agent,
        vault_agent,
        weather_agent,
    )

    registry = ToolRegistry()
    for module in (
        weather_agent,
        location_agent,
        news_agent,
        email_agent,
        messaging_agent,
        media_agent,
        memory_agent,
        vault_agent,
        automation_agent,
    ):
        module.register(registry)
    return registry
