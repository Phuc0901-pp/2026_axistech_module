"""ISO/IEC 27001 structured JSON logging with automatic secret/PII redaction."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any
import uuid

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|pwd|secret|token|cookie|set[-_]?cookie|authorization|"
    r"api[-_]?key|apikey|signature|credential|x-api-key|x-signature-256)",
    re.IGNORECASE,
)

_INLINE_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_INLINE_COOKIE_RE = re.compile(
    r"((?:Cookie|Set-Cookie|X-API-Key|Authorization)\s*[:=]\s*)([^\s;,\"]+)",
    re.IGNORECASE,
)


def get_or_create_correlation_id(explicit_id: str | None = None) -> str:
    """Return existing correlation ID in context, explicit ID, or generate a new UUIDv4."""
    if explicit_id and explicit_id.strip():
        cid = explicit_id.strip()
        correlation_id_var.set(cid)
        return cid
    current = correlation_id_var.get()
    if current:
        return current
    cid = str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def redact_string(text: str) -> str:
    """Mask inline Bearer tokens, cookies, and auth header values inside free text."""
    masked = _INLINE_BEARER_RE.sub(rf"\1{REDACTED}", text)
    masked = _INLINE_COOKIE_RE.sub(rf"\1{REDACTED}", masked)
    return masked


def redact_value(obj: Any, *, _key_hint: str = "") -> Any:
    """Recursively redact sensitive keys and inline credentials from dicts/lists/strings."""
    if _key_hint and _SENSITIVE_KEY_RE.search(_key_hint):
        return REDACTED
    if isinstance(obj, dict):
        return {
            str(k): (
                REDACTED if _SENSITIVE_KEY_RE.search(str(k)) else redact_value(v, _key_hint=str(k))
            )
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [redact_value(item) for item in obj]
    if isinstance(obj, str):
        return redact_string(obj)
    return obj


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line UTC JSON with correlation ID and redaction."""

    _STANDARD_ATTRS = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        message = redact_string(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "correlation_id": get_or_create_correlation_id(),
        }
        extras: dict[str, Any] = {}
        for k, v in record.__dict__.items():
            if k not in self._STANDARD_ATTRS and not k.startswith("_"):
                extras[k] = redact_value(v, _key_hint=k)
        if extras:
            payload["extra"] = extras
        if record.exc_info:
            payload["exception"] = redact_string(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root axisstream_bridge logger with ISO-27001 JsonFormatter."""
    logger = logging.getLogger("axisstream_bridge")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            handler.setFormatter(JsonFormatter())
    logger.propagate = False
    return logger
