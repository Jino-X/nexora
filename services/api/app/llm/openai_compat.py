"""OpenAI-compatible Chat Completions provider, used as an optional cloud fallback
(any vendor exposing /v1/chat/completions with tool calling)."""

from __future__ import annotations

import json
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


def to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            out.append({"role": "tool", "tool_call_id": msg.tool_call_id or "", "content": msg.content})
            continue
        item: dict[str, Any] = {"role": msg.role, "content": msg.content or None}
        if msg.tool_calls:
            item["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in msg.tool_calls
            ]
        out.append(item)
    return out


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.4,
    ) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: TokenCallback | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": self.temperature if temperature is None else temperature,
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens
        content: list[str] = []
        partial: dict[int, dict[str, Any]] = {}
        usage = Usage()
        think_filter = ThinkTagFilter()
        try:
            async with self.http.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=httpx.Timeout(self.timeout, connect=5.0),
            ) as res:
                if res.status_code in (401, 403):
                    raise LLMUnavailableError("Cloud LLM rejected the credentials")
                if res.status_code == 429 or res.status_code >= 500:
                    raise LLMUnavailableError(f"Cloud LLM unavailable ({res.status_code})")
                if res.status_code >= 400:
                    body = (await res.aread()).decode(errors="replace")[:300]
                    raise LLMError(f"Cloud LLM error {res.status_code}: {body}")
                async for line in res.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if u := chunk.get("usage"):
                        usage = Usage(
                            input_tokens=u.get("prompt_tokens") or 0, output_tokens=u.get("completion_tokens") or 0
                        )
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if text := delta.get("content"):
                            visible = think_filter.feed(text)
                            if visible:
                                content.append(visible)
                                if on_token:
                                    await on_token(visible)
                        for tc in delta.get("tool_calls") or []:
                            slot = partial.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise LLMUnavailableError("Cloud LLM is not reachable") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("Cloud LLM timed out") from exc
        calls = []
        for slot in partial.values():
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=slot["id"] or uuid.uuid4().hex[:12], name=slot["name"], arguments=args))
        tail = think_filter.flush()
        if tail:
            content.append(tail)
            if on_token:
                await on_token(tail)
        return LLMResponse(
            content="".join(content).strip(), tool_calls=calls, provider=self.name, model=self.model, usage=usage
        )
