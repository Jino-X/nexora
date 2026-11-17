"""Session lifecycle: limits, idle and false-trigger timeouts, cleanup and API notifications."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from livekit.agents import AgentSession

from nexora_voice.agent.instructions import FAREWELL, pick
from nexora_voice.config import Settings
from nexora_voice.orchestration.assistant_client import AssistantClient

logger = logging.getLogger("nexora.voice.lifecycle")


class SessionLifecycle:
    def __init__(
        self,
        *,
        settings: Settings,
        session: AgentSession,
        client: AssistantClient,
        session_id: str,
        room_name: str,
        activation: str,
        language: str,
        shutdown: Callable[[str], Awaitable[None]],
    ) -> None:
        self.settings = settings
        self.session = session
        self.client = client
        self.session_id = session_id
        self.room_name = room_name
        self.activation = activation
        self.language = language
        self._shutdown = shutdown
        self.started = time.monotonic()
        self.last_activity = time.monotonic()
        self.user_spoke = False
        self.ending = False
        self._task: asyncio.Task[None] | None = None

    def touch(self, *, user: bool = False) -> None:
        self.last_activity = time.monotonic()
        if user:
            self.user_spoke = True

    def start(self) -> None:
        self._task = asyncio.create_task(self._watchdog(), name="voice-watchdog")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def end(self, reason: str, farewell: str | None = None) -> None:
        if self.ending:
            return
        self.ending = True
        if farewell:
            try:
                handle = self.session.say(farewell, allow_interruptions=False)
                await asyncio.wait_for(handle.wait_for_playout(), timeout=8)
            except Exception:
                pass
        await self.client.post_event(
            session_id=self.session_id, room_name=self.room_name, event="session_ended", reason=reason
        )
        await self._shutdown(reason)

    async def _watchdog(self) -> None:
        while not self.ending:
            await asyncio.sleep(2)
            now = time.monotonic()
            if now - self.started > self.settings.max_session_seconds:
                await self.end("max_duration", pick(FAREWELL, self.language))
            elif (
                self.activation == "wake_word"
                and not self.user_spoke
                and now - self.started > self.settings.wake_word_no_speech_seconds
            ):
                logger.info("wake word session without speech; treating as a false trigger")
                await self.end("no_speech_after_wake_word")
            elif now - self.last_activity > self.settings.idle_timeout_seconds and self.session.agent_state in (
                "listening",
                "idle",
            ):
                await self.end("idle_timeout")
