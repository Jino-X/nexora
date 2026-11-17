"""Assistant runs with streamed (SSE) responses.

POST /assistant/runs                 start a run; the response is the SSE stream
GET  /assistant/runs/{id}/events     resume the stream (Last-Event-ID or ?after=N)
POST /assistant/runs/{id}/cancel     stop generation
GET  /assistant/runs/{id}            status + text so far
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, ServicesDep, rate_limit
from app.api.sse import parse_last_event_id, sse_response
from app.assistant.runs import Run
from app.assistant.service import TurnRequest, execute_turn, prepare_turn
from app.assistant.tools import Location
from app.schemas.resources import RunCreate, RunStatus

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/runs",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit("assistant", "assistant_rate_limit_per_minute"))],
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def start_run(body: RunCreate, user: CurrentUser, services: ServicesDep) -> StreamingResponse:
    req = TurnRequest(
        user_id=user.id,
        text=body.message,
        channel="text",
        conversation_id=body.conversation_id,
        location=Location(body.location.latitude, body.location.longitude, body.location.label)
        if body.location
        else None,
        language=body.language,
        regenerate=body.regenerate,
    )
    prepared = await prepare_turn(services, req)

    async def run_body(run: Run) -> None:
        await execute_turn(services, req, prepared, run)

    run = services.runs.start(user_id=user.id, conversation_id=prepared.conversation_id, channel="text", body=run_body)
    return sse_response(run)


@router.get("/runs/{run_id}/events", response_class=StreamingResponse)
async def resume_run(
    run_id: str,
    user: CurrentUser,
    services: ServicesDep,
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    run = services.runs.get(run_id, user.id)
    return sse_response(run, parse_last_event_id(last_event_id, after))


@router.post("/runs/{run_id}/cancel", response_model=RunStatus)
async def cancel_run(run_id: str, user: CurrentUser, services: ServicesDep) -> RunStatus:
    run = await services.runs.cancel(run_id, user.id)
    return RunStatus(
        run_id=run.id,
        conversation_id=run.conversation_id,
        status=run.status,
        event_count=len(run.events),
        text=run.text(),
    )


@router.get("/runs/{run_id}", response_model=RunStatus)
async def run_status(run_id: str, user: CurrentUser, services: ServicesDep) -> RunStatus:
    run = services.runs.get(run_id, user.id)
    return RunStatus(
        run_id=run.id,
        conversation_id=run.conversation_id,
        status=run.status,
        event_count=len(run.events),
        text=run.text(),
    )
