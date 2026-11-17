"""Structured logging with request correlation and secret redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)

SENSITIVE_KEYS = re.compile(
    r"(pass(word)?|secret|token|authorization|api[_-]?key|cookie|credential|refresh|private|ciphertext)",
    re.IGNORECASE,
)
# Bearer tokens, JWTs and common key prefixes that might slip into free-form messages.
SENSITIVE_VALUES = re.compile(
    r"(Bearer\s+[A-Za-z0-9._~+/=-]+|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+|"
    r"sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ya29\.[A-Za-z0-9_-]+|EAA[A-Za-z0-9]{20,})"
)


def redact(value: Any, depth: int = 0) -> Any:
    """Recursively redact values whose key looks sensitive, and token-like substrings."""
    if depth > 6:
        return "[depth]"
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if isinstance(k, str) and SENSITIVE_KEYS.search(k) else redact(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v, depth + 1) for v in value]
    if isinstance(value, str):
        return SENSITIVE_VALUES.sub("[redacted]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": SENSITIVE_VALUES.sub("[redacted]", record.getMessage()),
        }
        if rid := request_id_var.get():
            payload["request_id"] = rid
        if uid := user_id_var.get():
            payload["user_id"] = uid
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload["data"] = redact(extra)
        if record.exc_info:
            payload["exc"] = SENSITIVE_VALUES.sub("[redacted]", self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            base += " " + json.dumps(redact(extra), default=str)
        return SENSITIVE_VALUES.sub("[redacted]", base)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_logs else TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "aiosqlite", "sqlalchemy.engine.Engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, level: int, msg: str, **data: Any) -> None:
    logger.log(level, msg, extra={"data": data})
