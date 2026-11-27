"""Domain exception taxonomy for ISO/IEC 25010 & RFC 9457 error mapping."""

from __future__ import annotations

from typing import Any

from axisstream_bridge.core.logging import redact_value


class AxisStreamError(Exception):
    """Base exception for all AxisStream bridge domain and infrastructure failures."""

    code: str = "AXISSTREAM_ERROR"
    retryable: bool = False
    http_status_hint: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        http_status_hint: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        if http_status_hint is not None:
            self.http_status_hint = http_status_hint
        self.details: dict[str, Any] = redact_value(details or {})


class AuthenticationError(AxisStreamError):
    code = "AUTHENTICATION_FAILED"
    retryable = False
    http_status_hint = 401


class AuthorizationError(AxisStreamError):
    code = "AUTHORIZATION_DENIED"
    retryable = False
    http_status_hint = 403


class RateLimitError(AxisStreamError):
    code = "UPSTREAM_RATE_LIMITED"
    retryable = True
    http_status_hint = 429

    def __init__(
        self,
        message: str = "Upstream rate limit exceeded",
        *,
        retry_after: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after = retry_after


class UpstreamTransientError(AxisStreamError):
    code = "UPSTREAM_TRANSIENT_ERROR"
    retryable = True
    http_status_hint = 502


class SchemaDriftError(AxisStreamError):
    code = "UPSTREAM_SCHEMA_DRIFT"
    retryable = False
    http_status_hint = 502


class ValidationError(AxisStreamError):
    code = "VALIDATION_ERROR"
    retryable = False
    http_status_hint = 422


class CircuitOpenError(AxisStreamError):
    code = "CIRCUIT_BREAKER_OPEN"
    retryable = True
    http_status_hint = 503


class SecurityViolationError(AxisStreamError):
    code = "SECURITY_VIOLATION"
    retryable = False
    http_status_hint = 400
