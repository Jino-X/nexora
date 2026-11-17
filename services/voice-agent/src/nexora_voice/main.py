"""Nexora voice agent (LiveKit Agents 1.8).

    browser mic --WebRTC--> LiveKit --> this worker
      Silero VAD + turn detector -> STT (IndicConformer via speech server) ->
      Nexora core API (shared LangGraph graph, tools, approvals) -> TTS (Indic Parler-TTS) --> browser

Run locally:
    python -m nexora_voice.main download-files   # once: VAD + turn-detector weights
    python -m nexora_voice.main dev
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from dotenv import load_dotenv
from livekit.agents import (
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    ErrorEvent,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    UserInputTranscribedEvent,
    cli,
    room_io,
)
from livekit.plugins import silero

from nexora_voice.agent.assistant import NexoraVoiceAgent, ToolEventRelay
from nexora_voice.agent.instructions import GREETINGS, pick
from nexora_voice.agent.lifecycle import SessionLifecycle
from nexora_voice.audio.interruption import register_rpc_handlers
from nexora_voice.audio.turn_detection import build_turn_handling
from nexora_voice.config import get_settings
from nexora_voice.observability.metrics import TurnLatencyTracker
from nexora_voice.orchestration.assistant_client import AssistantClient
from nexora_voice.providers.factory import build_stt, build_tts
from nexora_voice.providers.llm.nexora_api import NexoraAssistantLLM
from nexora_voice.schemas.events import InvalidDispatchError, parse_dispatch_metadata

logger = logging.getLogger("nexora.voice")


def prewarm(proc: JobProcess) -> None:
    """Load the VAD once per worker process and reuse it across sessions."""
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=get_settings().livekit_agent_name)
async def entrypoint(ctx: JobContext) -> None:
    settings = get_settings()
    ctx.log_context_fields = {"room": ctx.room.name}
    try:
        meta = parse_dispatch_metadata(ctx.job.metadata)
    except InvalidDispatchError as exc:
        logger.error("refusing job: %s", exc)
        ctx.shutdown(reason="invalid_dispatch")
        return
    if not settings.nexora_internal_service_key:
        logger.error("NEXORA_INTERNAL_SERVICE_KEY is not set; cannot reach the assistant API")
        ctx.shutdown(reason="misconfigured")
        return

    http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    ctx.add_shutdown_callback(http.aclose)
    client = AssistantClient(
        http,
        base_url=settings.nexora_api_url,
        internal_key=settings.nexora_internal_service_key.get_secret_value(),
        timeout=settings.assistant_timeout_seconds,
    )
    session_id, room_name, owner = str(meta.voice_session_id), ctx.room.name, meta.participant_identity
    language = meta.language
    vad = ctx.proc.userdata["vad"]

    session: AgentSession = AgentSession(
        vad=vad,
        stt=build_stt(settings, http, vad, language),
        llm=NexoraAssistantLLM(
            client,
            session_id=session_id,
            room_name=room_name,
            participant_identity=owner,
            language=None if language == "auto" else language,
            on_event=ToolEventRelay(ctx.room, owner),
            timeout=settings.assistant_timeout_seconds,
        ),
        tts=build_tts(settings, http, language, meta.voice_name),
        turn_handling=build_turn_handling(settings, meta.turn_mode),
        tts_text_transforms=["filter_markdown", "filter_emoji"],
        user_away_timeout=None,  # SessionLifecycle owns idle handling
    )

    async def shutdown(reason: str) -> None:
        try:
            await ctx.delete_room()
        finally:
            ctx.shutdown(reason=reason)

    lifecycle = SessionLifecycle(
        settings=settings,
        session=session,
        client=client,
        session_id=session_id,
        room_name=room_name,
        activation=meta.activation,
        language=language,
        shutdown=shutdown,
    )
    tracker = TurnLatencyTracker()

    @session.on("user_input_transcribed")
    def _on_transcript(ev: UserInputTranscribedEvent) -> None:
        lifecycle.touch(user=bool(ev.transcript.strip()))

    @session.on("agent_state_changed")
    def _on_state(ev: AgentStateChangedEvent) -> None:
        lifecycle.touch()

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        done = tracker.add(ev.metrics)
        if done:
            asyncio.create_task(
                client.post_event(session_id=session_id, room_name=room_name, event="metrics", metrics=done.compact())
            )

    @session.on("error")
    def _on_error(ev: ErrorEvent) -> None:
        if getattr(ev.error, "recoverable", True):
            return
        logger.error("unrecoverable voice pipeline error: %s", type(ev.error).__name__)
        asyncio.create_task(lifecycle.end("provider_error"))

    # Connect before starting the session: with a participant_identity, RoomIO reads the room's local participant
    # while starting, which fails ("cannot access local participant before connecting") if the session's own
    # auto-connect hasn't happened yet. connect() is idempotent, so the session's later call is a no-op.
    await ctx.connect()
    await session.start(
        agent=NexoraVoiceAgent(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            participant_identity=owner,  # only the session owner's audio is ever processed
            text_input=False,
            close_on_disconnect=True,
            delete_room_on_close=True,
        ),
    )
    if meta.turn_mode == "manual":
        session.input.set_audio_enabled(False)
    register_rpc_handlers(ctx.room, session, owner_identity=owner, manual_turns=meta.turn_mode == "manual")
    await client.post_event(session_id=session_id, room_name=room_name, event="agent_joined")
    lifecycle.start()
    ctx.add_shutdown_callback(lifecycle.stop)

    greeting_lang = language if language in ("en", "ta") else "en"
    if meta.activation == "push_to_talk" and meta.turn_mode == "auto":
        session.say(pick(GREETINGS, greeting_lang))


if __name__ == "__main__":
    # LiveKit's worker reads LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET from the process environment rather
    # than from our settings, so load .env into it first (variables already set in the shell win).
    load_dotenv()
    cli.run_app(server)
