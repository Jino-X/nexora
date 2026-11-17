"""Browser -> agent RPCs: explicit interruption and hold-to-talk turn control.
Only the session owner (the one authorized participant) may call them."""

from __future__ import annotations

import logging

from livekit import rtc
from livekit.agents import AgentSession

from nexora_voice.schemas.events import RPC_CANCEL_TURN, RPC_END_TURN, RPC_INTERRUPT, RPC_START_TURN

logger = logging.getLogger("nexora.voice.rpc")


def register_rpc_handlers(room: rtc.Room, session: AgentSession, *, owner_identity: str, manual_turns: bool) -> None:
    def check(data: rtc.RpcInvocationData) -> None:
        if data.caller_identity != owner_identity:
            raise rtc.RpcError(rtc.RpcError.ErrorCode.APPLICATION_ERROR, "not the session owner")

    async def interrupt(data: rtc.RpcInvocationData) -> str:
        check(data)
        session.interrupt()
        return "ok"

    async def start_turn(data: rtc.RpcInvocationData) -> str:
        check(data)
        session.interrupt()
        session.clear_user_turn()
        session.input.set_audio_enabled(True)
        return "ok"

    async def end_turn(data: rtc.RpcInvocationData) -> str:
        check(data)
        session.input.set_audio_enabled(False)
        session.commit_user_turn(transcript_timeout=10.0, stt_flush_duration=2.0)
        return "ok"

    async def cancel_turn(data: rtc.RpcInvocationData) -> str:
        check(data)
        session.input.set_audio_enabled(False)
        session.clear_user_turn()
        return "ok"

    room.local_participant.register_rpc_method(RPC_INTERRUPT, interrupt)
    if manual_turns:
        room.local_participant.register_rpc_method(RPC_START_TURN, start_turn)
        room.local_participant.register_rpc_method(RPC_END_TURN, end_turn)
        room.local_participant.register_rpc_method(RPC_CANCEL_TURN, cancel_turn)
