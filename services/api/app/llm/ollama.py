"""Ollama chat provider (default: Qwen3 8B) using the native /api/chat streaming endpoint."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from app.llm.base import (
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMResponse,
    LLMUnavailableError,
    ThinkTagFilter,
    TokenCallback,
    ToolCall,
    Usage,
)

logger = logging.getLogger("nexora.llm.ollama")

THINKING_FAMILIES = ("qwen3", "deepseek-r1", "gpt-oss", "magistral")


def to_ollama_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        item: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            item["tool_calls"] = [
                {"type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in msg.tool_calls
            ]
        if msg.role == "tool" and msg.name:
            item["tool_name"] = msg.name
        out.append(item)
    return out


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str,
        model: str,
        think: bool = False,
        keep_alive: str = "30m",
        num_ctx: int = 8192,
        timeout: float = 90.0,
        temperature: float = 0.4,
    ) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.think = think
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.temperature = temperature

    def _payload(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": self.temperature if temperature is None else temperature,
            "num_ctx": self.num_ctx,
        }
        if max_tokens:
            options["num_predict"] = max_tokens
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_ollama_messages(messages),
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if tools:
            payload["tools"] = tools
        if any(f in self.model for f in THINKING_FAMILIES):
            payload["think"] = self.think
        return payload

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: TokenCallback | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload = self._payload(messages, tools, temperature, max_tokens)
        content: list[str] = []
        calls: list[ToolCall] = []
        usage = Usage()
        think_filter = ThinkTagFilter()
        try:
            async with self.http.stream(
                "POST", f"{self.base_url}/api/chat", json=payload, timeout=httpx.Timeout(self.timeout, connect=3.0)
            ) as res:
                if res.status_code == 404:
                    raise LLMUnavailableError(f"Ollama model '{self.model}' is not available (ollama pull)")
                if res.status_code >= 400:
                    body = (await res.aread()).decode(errors="replace")[:300]
                    raise LLMError(f"Ollama error {res.status_code}: {body}")
                async for line in res.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if err := chunk.get("error"):
                        raise LLMError(f"Ollama error: {err}")
                    message = chunk.get("message") or {}
                    if text := message.get("content"):
                        visible = think_filter.feed(text)
                        if visible:
                            content.append(visible)
                            if on_token:
                                await on_token(visible)
                    for call in message.get("tool_calls") or []:
                        fn = call.get("function") or {}
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        calls.append(
                            ToolCall(
                                id=call.get("id") or uuid.uuid4().hex[:12], name=fn.get("name", ""), arguments=args
                            )
                        )
                    if chunk.get("done"):
                        usage = Usage(
                            input_tokens=chunk.get("prompt_eval_count") or 0, output_tokens=chunk.get("eval_count") or 0
                        )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise LLMUnavailableError("Ollama is not reachable") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("Ollama timed out") from exc
        tail = think_filter.flush()
        if tail:
            content.append(tail)
            if on_token:
                await on_token(tail)
        return LLMResponse(
            content="".join(content).strip(), tool_calls=calls, provider=self.name, model=self.model, usage=usage
        )

    async def health(self) -> bool:
        try:
            res = await self.http.get(f"{self.base_url}/api/tags", timeout=2.0)
            if res.status_code != 200:
                return False
            names = {m.get("name") for m in res.json().get("models", [])}
            return self.model in names or f"{self.model}:latest" in names
        except httpx.HTTPError:
            return False
