"""LiveKit `llm.LLM` adapter whose "model" is the Nexora assistant service.

The voice pipeline needs an LLM object. This one forwards the user's finished utterance to the core
API and streams the reply tokens back for TTS. All reasoning, memory, tools and approvals run
server-side in the shared LangGraph graph, so nothing is duplicated here. Conversation history also
lives server-side (the voice session's conversation), so only the latest user message is sent."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from livekit.agents import APIConnectionError, APIConnectOptions, APIStatusError, llm
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import shortuuid

from nexora_voice.orchestration.assistant_client import AssistantAPIError, AssistantClient
from nexora_voice.schemas.events import AssistantEvent

logger = logging.getLogger("nexora.voice.llm")

EventHook = Callable[[AssistantEvent], Awaitable[None]]


def latest_user_text(chat_ctx: llm.ChatContext) -> str:
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and getattr(item, "role", None) == "user":
            text = item.text_content or ""
            if text.strip():
                return text.strip()
    return ""


class NexoraAssistantLLM(llm.LLM):
    def __init__(
        self,
        client: AssistantClient,
        *,
        session_id: str,
        room_name: str,
        participant_identity: str,
        language: str | None,
        on_event: EventHook | None = None,
        timeout: float = 60.0,
    ) -> None:
        super().__init__()
        self.client = client
        self.session_id = session_id
        self.room_name = room_name
        self.participant_identity = participant_identity
        self.language = language
        self.on_event = on_event
        self.timeout = timeout

    @property
    def model(self) -> str:
        return "nexora-assistant"

    @property
    def provider(self) -> str:
        return "nexora"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = APIConnectOptions(),
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[Any] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> NexoraAssistantStream:
        # No automatic retries: the API stores the user message when a turn starts, so a retry would
        # duplicate it. Failures surface as an error the agent apologises for.
        options = APIConnectOptions(max_retry=0, timeout=self.timeout, retry_interval=conn_options.retry_interval)
        return NexoraAssistantStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=options)


class NexoraAssistantStream(llm.LLMStream):
    def __init__(
        self,
        llm_: NexoraAssistantLLM,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(llm_, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._nexora = llm_

    def _say(self, request_id: str, text: str) -> None:
        self._event_ch.send_nowait(llm.ChatChunk(id=request_id, delta=llm.ChoiceDelta(role="assistant", content=text)))

    async def _run(self) -> None:
        text = latest_user_text(self._chat_ctx)
        if not text:
            return
        request_id = shortuuid()
        spoke = False
        try:
            async for event in self._nexora.client.stream_turn(
                session_id=self._nexora.session_id,
                room_name=self._nexora.room_name,
                participant_identity=self._nexora.participant_identity,
                text=text,
                language=self._nexora.language,
            ):
                if event.event == "token":
                    token = str(event.data.get("text", ""))
                    if token:
                        spoke = True
                        self._say(request_id, token)
                elif event.event == "error":
                    logger.warning("assistant reported an error: %s", event.data.get("code"))
                    if not spoke:
                        self._say(request_id, apology(self._nexora.language))
                    return
                if self._nexora.on_event and event.event in (
                    "tool_start",
                    "tool_end",
                    "approval_required",
                    "message_end",
                ):
                    await self._nexora.on_event(event)
                if event.event == "message_end" and not spoke:
                    # Offline/template answers may arrive only in message_end.
                    content = str(event.data.get("content", ""))
                    if content:
                        self._say(request_id, content)
        except AssistantAPIError as exc:
            logger.warning("assistant turn failed: %s", exc)
            if exc.status in (401, 403, 409):
                # Session no longer valid (ended, expired, or identity mismatch): stop the pipeline.
                raise APIStatusError(str(exc), status_code=exc.status, retryable=False) from exc
            if not spoke:
                self._say(request_id, apology(self._nexora.language))
            if exc.retryable:
                raise APIConnectionError(str(exc), retryable=False) from exc


def apology(language: str | None) -> str:
    from nexora_voice.agent.instructions import ERROR_REPLY, pick

    return pick(ERROR_REPLY, language or "en")
