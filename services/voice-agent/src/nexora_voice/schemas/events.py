"""Typed contracts with the core API and the browser."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

# Must match packages/shared-types VOICE_PROTOCOL.
RPC_INTERRUPT = "nexora.interrupt"
RPC_START_TURN = "nexora.start_turn"
RPC_END_TURN = "nexora.end_turn"
RPC_CANCEL_TURN = "nexora.cancel_turn"
NOTICE_TOPIC = "nexora.notice"
TOOL_TOPIC = "nexora.tool"


class DispatchMetadata(BaseModel):
    """Set by the API when it mints the participant token (RoomAgentDispatch.metadata)."""

    voice_session_id: uuid.UUID
    participant_identity: str = Field(min_length=1, max_length=128)  # the only participant the agent serves
    activation: Literal["push_to_talk", "wake_word"] = "push_to_talk"
    turn_mode: Literal["auto", "manual"] = "auto"
    language: str = "auto"
    voice_name: str | None = None
    speaking_rate: float = 1.0
    store_recordings: bool = False


class InvalidDispatchError(ValueError):
    pass


def parse_dispatch_metadata(raw: str | None) -> DispatchMetadata:
    if not raw:
        raise InvalidDispatchError("missing dispatch metadata (job must be dispatched by the Nexora API)")
    try:
        return DispatchMetadata.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidDispatchError(f"invalid dispatch metadata: {exc}") from exc


class AssistantEvent(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    id: int | None = None


class TurnMetrics(BaseModel):
    eou_delay_ms: float | None = None
    stt_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None
    end_to_end_ms: float | None = None

    def compact(self) -> dict[str, float]:
        return {k: round(v, 1) for k, v in self.model_dump().items() if v is not None}
