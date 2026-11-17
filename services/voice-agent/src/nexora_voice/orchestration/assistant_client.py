"""Client for the core API's internal voice endpoints.

Every turn goes through POST /api/v1/internal/voice/turns, which runs the same LangGraph assistant
(same tools, permissions and approvals) as text chat. The API checks that the session id, room and
participant identity match an active voice session before running anything."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from nexora_voice.schemas.events import AssistantEvent

logger = logging.getLogger("nexora.voice.api")


class AssistantAPIError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


async def parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[AssistantEvent]:
    event, data, ident = None, [], None
    async for line in lines:
        if line == "":
            if event and data:
                try:
                    payload = json.loads("\n".join(data))
                except json.JSONDecodeError:
                    payload = {"raw": "\n".join(data)}
                yield AssistantEvent(event=event, data=payload if isinstance(payload, dict) else {}, id=ident)
            event, data, ident = None, [], None
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
        elif field == "id" and value.isdigit():
            ident = int(value)


class AssistantClient:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str, internal_key: str, timeout: float = 60.0) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Nexora-Internal-Key": internal_key}
        self.timeout = timeout

    async def stream_turn(
        self, *, session_id: str, room_name: str, participant_identity: str, text: str, language: str | None
    ) -> AsyncIterator[AssistantEvent]:
        body: dict[str, Any] = {
            "session_id": session_id,
            "room_name": room_name,
            "participant_identity": participant_identity,
            "text": text,
        }
        if language in ("en", "ta"):
            body["language"] = language
        try:
            async with self.http.stream(
                "POST",
                f"{self.base_url}/api/v1/internal/voice/turns",
                json=body,
                headers=self.headers,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
            ) as res:
                if res.status_code >= 400:
                    detail = (await res.aread()).decode(errors="replace")[:300]
                    raise AssistantAPIError(
                        f"assistant API returned {res.status_code}: {detail}",
                        status=res.status_code,
                        retryable=res.status_code >= 500,
                    )
                async for event in parse_sse(res.aiter_lines()):
                    yield event
        except httpx.TimeoutException as exc:
            raise AssistantAPIError("assistant API timed out", retryable=False) from exc
        except httpx.HTTPError as exc:
            raise AssistantAPIError(f"assistant API unreachable: {type(exc).__name__}", retryable=True) from exc

    async def post_event(
        self,
        *,
        session_id: str,
        room_name: str,
        event: str,
        reason: str | None = None,
        metrics: dict[str, float] | None = None,
    ) -> None:
        body: dict[str, Any] = {"session_id": session_id, "room_name": room_name, "event": event}
        if reason:
            body["reason"] = reason[:64]
        if metrics:
            body["metrics"] = metrics
        try:
            await self.http.post(
                f"{self.base_url}/api/v1/internal/voice/events", json=body, headers=self.headers, timeout=5.0
            )
        except httpx.HTTPError as exc:  # telemetry must never break the session
            logger.warning("voice event %s not delivered: %s", event, type(exc).__name__)
