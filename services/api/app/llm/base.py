"""Provider-neutral chat model interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]
TokenCallback = Callable[[str], Awaitable[None]]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None  # tool name for role="tool"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    offline: bool = False


class LLMError(Exception):
    """The provider answered but the request failed."""


class LLMUnavailableError(LLMError):
    """The provider is unreachable or not ready; callers may fall back to another provider."""


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""
    offline: bool = False

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: TokenCallback | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    async def health(self) -> bool:
        return True


class ThinkTagFilter:
    """Removes <think>...</think> blocks from a token stream (Qwen3 reasoning traces)."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        out: list[str] = []
        while self._buffer:
            if self._inside:
                end = self._buffer.find(self.CLOSE)
                if end == -1:
                    keep = len(self.CLOSE) - 1
                    self._buffer = self._buffer[-keep:] if len(self._buffer) > keep else self._buffer
                    return "".join(out)
                self._buffer = self._buffer[end + len(self.CLOSE) :]
                self._inside = False
                continue
            start = self._buffer.find(self.OPEN)
            if start == -1:
                # Hold back a possible partial "<think" at the end.
                safe = len(self._buffer)
                for i in range(1, len(self.OPEN)):
                    if self._buffer.endswith(self.OPEN[:i]):
                        safe = len(self._buffer) - i
                        break
                out.append(self._buffer[:safe])
                self._buffer = self._buffer[safe:]
                return "".join(out)
            out.append(self._buffer[:start])
            self._buffer = self._buffer[start + len(self.OPEN) :]
            self._inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._inside else self._buffer
        self._buffer = ""
        return rest
