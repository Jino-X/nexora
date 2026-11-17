"""Voice sessions.

Public (user JWT):
  POST /voice/sessions               create a session + short-lived LiveKit token
  POST /voice/sessions/{id}/end      end it (also deletes the LiveKit room)
  GET  /voice/sessions               history

Internal (voice agent, X-Nexora-Internal-Key):
  POST /internal/voice/turns         run one assistant turn for a verified session (SSE)
  POST /internal/voice/events        lifecycle + latency metrics
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, ServicesDep, rate_limit, require_internal
from app.api.sse import sse_response
from app.assistant.runs import Run
from app.assistant.service import TurnRequest, execute_turn, prepare_turn
from app.core.exceptions import ConflictError, PermissionDeniedError
from app.database import models as m
from app.database import repositories as repo
from app.database.base import utcnow
from app.schemas.common import OkResponse, Page
from app.schemas.resources import (
    VoiceSessionCreate,
    VoiceSessionEventIn,
    VoiceSessionOut,
    VoiceSessionSummary,
    VoiceTurnIn,
)

router = APIRouter(prefix="/voice", tags=["voice"])
internal = APIRouter(prefix="/internal/voice", tags=["internal"], dependencies=[Depends(require_internal)])


@router.post(
    "/sessions",
    response_model=VoiceSessionOut,
    status_code=201,
    dependencies=[Depends(rate_limit("voice", "voice_rate_limit_per_minute"))],
)
async def create_session(body: VoiceSessionCreate, user: CurrentUser, db: DB, services: ServicesDep) -> VoiceSessionOut:
    services.livekit._require()
    # One live session per user: end any stale ones first.
    stale = (
        (
            await db.execute(
                select(m.VoiceSession).where(
                    m.VoiceSession.user_id == user.id, m.VoiceSession.status.in_(("created", "active"))
                )
            )
        )
        .scalars()
        .all()
    )
    for old in stale:
        old.status, old.ended_at, old.end_reason = "ended", utcnow(), "superseded"
        await services.livekit.delete_room(old.room_name)

    if body.conversation_id:
        conv = await repo.get_owned(db, m.Conversation, user.id, body.conversation_id, label="Conversation")
    else:
        conv = await repo.create_conversation(db, user.id, title="Voice conversation", channel="voice")
    prefs = await repo.get_preferences(db, user.id)
    profile = await db.get(m.Profile, user.id)
    session_id = uuid.uuid4()
    room = f"nxr-{session_id.hex}"
    expires = utcnow() + timedelta(seconds=services.settings.voice_token_ttl_seconds)
    language = body.language or prefs.preferred_language
    vs = m.VoiceSession(
        id=session_id,
        user_id=user.id,
        room_name=room,
        activation=body.activation,
        language=language,
        conversation_id=conv.id,
        expires_at=expires,
    )
    db.add(vs)
    await db.flush()
    identity = str(user.id)
    token = services.livekit.create_participant_token(
        identity=identity,
        name=profile.display_name if profile else None,
        room=room,
        agent_metadata={
            "voice_session_id": str(session_id),
            "participant_identity": identity,
            "activation": body.activation,
            "turn_mode": "manual" if body.hold_to_talk and body.activation == "push_to_talk" else "auto",
            "language": language,
            "voice_name": prefs.voice_name,
            "speaking_rate": prefs.voice_speaking_rate,
            "store_recordings": prefs.store_voice_recordings,
        },
    )
    await repo.audit(
        db,
        user.id,
        action="voice.session_created",
        resource_type="voice_session",
        resource_id=str(session_id),
        details={"activation": body.activation},
    )
    assert services.settings.livekit_url
    return VoiceSessionOut(
        session_id=session_id,
        room_name=room,
        server_url=services.settings.livekit_url,
        participant_token=token,
        participant_identity=identity,
        conversation_id=conv.id,
        expires_at=expires,
    )


@router.post("/sessions/{session_id}/end", response_model=OkResponse)
async def end_session(session_id: uuid.UUID, user: CurrentUser, db: DB, services: ServicesDep) -> OkResponse:
    vs = await repo.get_owned(db, m.VoiceSession, user.id, session_id, label="Voice session")
    if vs.status in ("created", "active"):
        vs.status, vs.ended_at, vs.end_reason = "ended", utcnow(), "user"
        await services.livekit.delete_room(vs.room_name)
    return OkResponse()


@router.get("/sessions", response_model=Page[VoiceSessionSummary])
async def list_sessions(
    user: CurrentUser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Page[VoiceSessionSummary]:
    stmt = select(m.VoiceSession).where(m.VoiceSession.user_id == user.id).order_by(m.VoiceSession.created_at.desc())
    rows, more = await repo.paginate(db, stmt, limit, offset)
    return Page.of([VoiceSessionSummary.model_validate(r) for r in rows], more, offset, limit)


async def _verified_session(
    db: Any, session_id: uuid.UUID, room_name: str, identity: str, max_seconds: int
) -> m.VoiceSession:
    """The agent may only act for the session owner, in the session's own room, while it is live."""
    vs = await db.get(m.VoiceSession, session_id)
    if vs is None or vs.room_name != room_name:
        raise PermissionDeniedError("Voice session does not match this room", code="room_mismatch")
    if identity != str(vs.user_id):
        raise PermissionDeniedError("Participant is not the session owner", code="identity_mismatch")
    if vs.status not in ("created", "active"):
        raise ConflictError(f"Voice session is {vs.status}", code="session_closed")
    if utcnow() > vs.created_at + timedelta(seconds=max_seconds):
        vs.status, vs.ended_at, vs.end_reason = "expired", utcnow(), "max_duration"
        await db.commit()
        raise ConflictError("Voice session reached its maximum duration", code="session_expired")
    return vs


@internal.post("/turns", response_class=StreamingResponse)
async def voice_turn(body: VoiceTurnIn, db: DB, services: ServicesDep) -> StreamingResponse:
    vs = await _verified_session(
        db, body.session_id, body.room_name, body.participant_identity, services.settings.voice_max_session_seconds
    )
    vs.status = "active"
    vs.started_at = vs.started_at or utcnow()
    vs.turn_count += 1
    user_id, conversation_id = vs.user_id, vs.conversation_id
    language = body.language if body.language in ("en", "ta") else None
    await db.commit()

    req = TurnRequest(
        user_id=user_id,
        text=body.text,
        channel="voice",
        conversation_id=conversation_id,
        language=language or (vs.language if vs.language != "auto" else None),
    )
    prepared = await prepare_turn(services, req)

    async def run_body(run: Run) -> None:
        await execute_turn(services, req, prepared, run)

    run = services.runs.start(user_id=user_id, conversation_id=prepared.conversation_id, channel="voice", body=run_body)
    # Barge-in: when the agent drops the stream, cancel the run to save compute.
    return sse_response(run, cancel_on_disconnect=True)


@internal.post("/events", response_model=OkResponse)
async def voice_event(body: VoiceSessionEventIn, db: DB, services: ServicesDep) -> OkResponse:
    vs = await db.get(m.VoiceSession, body.session_id)
    if vs is None or vs.room_name != body.room_name:
        raise PermissionDeniedError("Voice session does not match this room", code="room_mismatch")
    now = utcnow()
    if body.event in ("agent_joined", "session_started") and vs.status == "created":
        vs.status, vs.started_at = "active", now
    elif body.event == "session_ended" and vs.status in ("created", "active"):
        vs.status, vs.ended_at, vs.end_reason = "ended", now, (body.reason or "agent")[:64]
    elif body.event == "metrics" and body.metrics:
        meta = dict(vs.meta or {})
        samples = list(meta.get("latency_samples", []))[-49:]
        samples.append({k: round(v, 1) for k, v in body.metrics.items()})
        meta["latency_samples"] = samples
        vs.meta = meta
        db.add(
            m.ExecutionLog(
                user_id=vs.user_id,
                run_id=str(vs.id),
                event_type="voice_metrics",
                name="voice_turn",
                status="ok",
                duration_ms=int(body.metrics.get("end_to_end_ms", 0)),
                details=body.metrics,
            )
        )
    return OkResponse()
