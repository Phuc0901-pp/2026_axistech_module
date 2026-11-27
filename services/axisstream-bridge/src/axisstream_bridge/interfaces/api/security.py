"""Inbound API Key guard (constant-time) and Correlation-ID middleware (ISO 27001)."""

from __future__ import annotations

import hmac
from typing import Callable

from fastapi import Depends, Header, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import AuthenticationError
from axisstream_bridge.core.logging import get_or_create_correlation_id


class CorrelationAndSecurityMiddleware(BaseHTTPMiddleware):
    """Attaches X-Correlation-ID and ISO 27001 security headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming_cid = request.headers.get("X-Correlation-ID")
        cid = get_or_create_correlation_id(incoming_cid)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


def require_api_key(settings: BridgeSettings):
    """Dependency validating X-API-Key with constant-time hmac.compare_digest."""

    async def _verify(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
        expected = settings.inbound_api_key.get_secret_value()
        if not x_api_key or not hmac.compare_digest(x_api_key.encode("utf-8"), expected.encode("utf-8")):
            raise AuthenticationError("Missing or invalid X-API-Key")
        return "authorized"

    return Depends(_verify)
