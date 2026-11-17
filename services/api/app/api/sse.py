"""Server-Sent Events for assistant runs (resumable with Last-Event-ID)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.assistant.runs import Run

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def format_event(seq: int, event: str, data: dict[str, object]) -> str:
    return f"id: {seq}\nevent: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


async def _stream(run: Run, after: int, cancel_on_disconnect: bool) -> AsyncIterator[str]:
    yield "retry: 2000\n\n"
    finished = False
    try:
        async for event in run.subscribe(after):
            if event is None:
                yield ": keep-alive\n\n"
                continue
            yield format_event(event.seq, event.type, event.data)
        finished = True
        yield format_event(len(run.events) + 1, "done", {"status": run.status})
    finally:
        if not finished and cancel_on_disconnect and run.task and not run.task.done():
            run.task.cancel()


def sse_response(run: Run, after: int = 0, *, cancel_on_disconnect: bool = False) -> StreamingResponse:
    return StreamingResponse(
        _stream(run, after, cancel_on_disconnect), media_type="text/event-stream", headers=SSE_HEADERS
    )


def parse_last_event_id(header: str | None, query: int | None) -> int:
    if query is not None:
        return max(0, query)
    if header and header.strip().isdigit():
        return int(header.strip())
    return 0
