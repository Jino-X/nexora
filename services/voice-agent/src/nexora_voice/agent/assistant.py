"""The voice agent. It owns only real-time concerns. Turns are answered by the core API through
`NexoraAssistantLLM`; tool progress is relayed to the browser as data messages."""

from __future__ import annotations

import json
import logging

from livekit import rtc
from livekit.agents import Agent

from nexora_voice.agent.instructions import AGENT_INSTRUCTIONS
from nexora_voice.schemas.events import TOOL_TOPIC, AssistantEvent

logger = logging.getLogger("nexora.voice.agent")


class NexoraVoiceAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=AGENT_INSTRUCTIONS)


class ToolEventRelay:
    """Forwards tool and approval events to the user's browser (topic `nexora.tool`) so the UI can show
    cards and approval prompts during a voice conversation."""

    def __init__(self, room: rtc.Room, owner_identity: str) -> None:
        self.room = room
        self.owner_identity = owner_identity

    async def __call__(self, event: AssistantEvent) -> None:
        payload = {"event": event.event, "data": event.data}
        try:
            await self.room.local_participant.send_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                topic=TOOL_TOPIC,
                destination_identities=[self.owner_identity],
            )
        except Exception as exc:  # UI hints are best-effort
            logger.debug("tool event relay failed: %s", exc)
