"""Assistant runs: asyncio tasks decoupled from HTTP connections.

Each run buffers its events in sequence. A client that loses its SSE connection reconnects with
`Last-Event-ID` and receives only the missed events. `cancel()` stops generation. Buffers are
in-process. With several API replicas, use sticky sessions or move the buffer to Redis Streams
(see docs/deployment.md). The persisted messages are the durable record either way."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import NotFoundError, RateLimitedError

logger = logging.getLogger("nexora.runs")


@dataclass
class RunEvent:
    seq: int
    type: str
    data: dict[str, Any]


@dataclass
class Run:
    id: str
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    channel: str
    events: list[RunEvent] = field(default_factory=list)
    status: str = "running"  # running | completed | failed | cancelled
    created_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    task: asyncio.Task[None] | None = None
    _cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def done(self) -> bool:
        return self.status != "running"

    async def emit(self, type_: str, data: dict[str, Any] | None = None) -> None:
        async with self._cond:
            self.events.append(RunEvent(len(self.events) + 1, type_, data or {}))
            self._cond.notify_all()

    async def finish(self, status: str) -> None:
        async with self._cond:
            if self.status == "running":
                self.status = status
                self.finished_at = time.monotonic()
            self._cond.notify_all()

    async def subscribe(self, after: int = 0, keepalive: float = 15.0) -> AsyncIterator[RunEvent | None]:
        """Yields events with seq > after; yields None as a keep-alive tick while idle."""
        index = max(0, after)
        while True:
            async with self._cond:
                if index >= len(self.events) and not self.done:
                    try:
                        await asyncio.wait_for(self._cond.wait(), keepalive)
                    except TimeoutError:
                        pass
                batch = self.events[index:]
                done = self.done
            if not batch and not done:
                yield None
            for event in batch:
                yield event
            index += len(batch)
            if done and index >= len(self.events):
                return

    def text(self) -> str:
        return "".join(e.data.get("text", "") for e in self.events if e.type == "token")


RunBody = Callable[[Run], Awaitable[None]]


class RunManager:
    def __init__(self, ttl_seconds: float = 600, max_per_user: int = 3) -> None:
        self.ttl = ttl_seconds
        self.max_per_user = max_per_user
        self._runs: dict[str, Run] = {}

    def start(self, *, user_id: uuid.UUID, conversation_id: uuid.UUID, channel: str, body: RunBody) -> Run:
        self.cleanup()
        active = sum(1 for r in self._runs.values() if r.user_id == user_id and not r.done)
        if active >= self.max_per_user:
            raise RateLimitedError("Too many assistant requests in progress. Wait for one to finish.")
        run = Run(id=uuid.uuid4().hex, user_id=user_id, conversation_id=conversation_id, channel=channel)
        self._runs[run.id] = run
        run.task = asyncio.create_task(self._drive(run, body), name=f"run-{run.id}")
        return run

    async def _drive(self, run: Run, body: RunBody) -> None:
        try:
            await body(run)
            await run.finish("completed")
        except asyncio.CancelledError:
            await run.emit("cancelled", {"reason": "stopped"})
            await run.finish("cancelled")
        except Exception:
            logger.exception("assistant run failed")
            await run.emit("error", {"code": "internal_error", "message": "Something went wrong. Please retry."})
            await run.finish("failed")

    def get(self, run_id: str, user_id: uuid.UUID) -> Run:
        run = self._runs.get(run_id)
        if run is None or run.user_id != user_id:
            raise NotFoundError("Run not found or expired")
        return run

    async def cancel(self, run_id: str, user_id: uuid.UUID) -> Run:
        run = self.get(run_id, user_id)
        if run.task and not run.task.done():
            run.task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(run.task), timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                pass
        return run

    def cleanup(self) -> None:
        now = time.monotonic()
        for rid in [rid for rid, r in self._runs.items() if r.finished_at and now - r.finished_at > self.ttl]:
            del self._runs[rid]

    async def shutdown(self) -> None:
        tasks = [r.task for r in self._runs.values() if r.task and not r.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
