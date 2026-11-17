"""ASGI middleware: request ids, body size limits and security headers."""

from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var, user_id_var


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode()[:64]
        rid = incoming if incoming and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        user_token = user_id_var.set(None)
        start = time.perf_counter()

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                hdrs: list[Any] = list(message.get("headers") or [])
                hdrs.append((b"x-request-id", rid.encode()))
                hdrs.append((b"x-content-type-options", b"nosniff"))
                hdrs.append((b"referrer-policy", b"no-referrer"))
                hdrs.append((b"x-frame-options", b"DENY"))
                hdrs.append((b"server-timing", f"app;dur={(time.perf_counter() - start) * 1000:.1f}".encode()))
                message["headers"] = hdrs
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            request_id_var.reset(token)
            user_id_var.reset(user_token)


class BodySizeLimitMiddleware:
    """Rejects bodies above `max_bytes`, both by Content-Length and while streaming chunked bodies."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await _too_large(send)
            return

        received = 0

        async def _receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, _receive, send)
        except _BodyTooLarge:
            await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send: Send) -> None:
    body = b'{"error":{"code":"payload_too_large","message":"Request body too large"}}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
