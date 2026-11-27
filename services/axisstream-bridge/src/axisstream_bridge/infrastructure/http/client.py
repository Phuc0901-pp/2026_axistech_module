"""Resilient HTTPS client with strict TLS, host whitelist, retry/jitter, circuit breaker, and auth replay."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from axisstream_bridge.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CircuitOpenError,
    RateLimitError,
    SecurityViolationError,
    UpstreamTransientError,
    ValidationError,
)
from axisstream_bridge.domain.ports import AuthPort
from axisstream_bridge.infrastructure.http.circuit_breaker import CircuitBreaker
from axisstream_bridge.infrastructure.http.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("axisstream_bridge.http")

TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})


class ResilientHttpClient:
    """Async HTTPS transport wrapping httpx with ISO 25010 & ISO 27001 controls."""

    def __init__(
        self,
        *,
        allowed_host_suffix: str = ".axisstream.co",
        timeout_sec: float = 15.0,
        max_retries: int = 3,
        base_backoff_sec: float = 0.2,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        auth: AuthPort | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        jitter_fn: Callable[[float, float], float] | None = None,
    ) -> None:
        self.allowed_host_suffix = allowed_host_suffix.lower().lstrip("*")
        self.max_retries = max_retries
        self.base_backoff_sec = base_backoff_sec
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter()
        self.auth = auth
        self._sleeper = sleeper or asyncio.sleep
        self._jitter_fn = jitter_fn or random.uniform
        self._client = httpx.AsyncClient(
            verify=True,
            follow_redirects=False,
            timeout=httpx.Timeout(
                connect=min(5.0, timeout_sec),
                read=timeout_sec,
                write=timeout_sec,
                pool=timeout_sec,
            ),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _validate_target_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise SecurityViolationError(f"Blocked non-HTTPS request URL: {url!r}")
        host = (parsed.hostname or "").lower()
        suffix = self.allowed_host_suffix
        if suffix and not (host == suffix.lstrip(".") or host.endswith(suffix)):
            raise SecurityViolationError(
                f"Blocked request to non-whitelisted host {host!r}"
            )

    def _compute_backoff(self, attempt: int, retry_after_header: str | None) -> float:
        if retry_after_header:
            try:
                val = float(retry_after_header.strip())
                if val >= 0:
                    return val
            except ValueError:
                pass
        cap = self.base_backoff_sec * (2**attempt)
        return self._jitter_fn(0.0, cap)

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = await self.request_raw(
            method, url, params=params, json_body=json_body, headers=headers
        )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamTransientError("Upstream returned invalid JSON payload") from exc

    async def request_raw(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self._validate_target_url(url)

        auth_retried = False
        attempt = 0

        while True:
            if not self.circuit_breaker.allow_request():
                raise CircuitOpenError("Upstream circuit breaker is OPEN")

            await self.rate_limiter.acquire()

            req_headers: dict[str, str] = {"Accept": "application/json"}
            req_cookies: dict[str, str] = {}
            auth_gen = 0
            if self.auth is not None:
                req_headers.update(await self.auth.get_auth_headers())
                req_cookies.update(await self.auth.get_auth_cookies())
                auth_gen = self.auth.generation
            if req_cookies:
                cookie_header = "; ".join(f"{k}={v}" for k, v in req_cookies.items())
                req_headers["Cookie"] = cookie_header
            if headers:
                req_headers.update(headers)

            try:
                resp = await self._client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_body,
                    headers=req_headers,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                self.circuit_breaker.record_failure()
                if attempt < self.max_retries:
                    delay = self._compute_backoff(attempt, None)
                    attempt += 1
                    logger.warning(
                        "Upstream transport error, retrying",
                        extra={"attempt": attempt, "delay_sec": round(delay, 3)},
                    )
                    await self._sleeper(delay)
                    continue
                raise UpstreamTransientError(
                    f"Upstream request failed after {attempt} retries: {type(exc).__name__}"
                ) from exc

            # Block unsafe cross-domain redirects (SSRF / Cookie leakage protection)
            if 300 <= resp.status_code < 400:
                location = resp.headers.get("location", "")
                if location:
                    self._validate_target_url(location)
                raise SecurityViolationError(
                    f"Unexpected redirect status {resp.status_code} blocked"
                )

            # Single-flight 401 session refresh + 1 replay
            if resp.status_code == 401:
                if self.auth is not None and not auth_retried:
                    auth_retried = True
                    await self.auth.refresh_session(auth_gen)
                    continue
                raise AuthenticationError("Upstream authentication failed (401)")

            if resp.status_code == 403:
                raise AuthorizationError("Upstream authorization denied (403)")

            if resp.status_code in (400, 404, 422):
                raise ValidationError(
                    f"Upstream rejected request with status {resp.status_code}",
                    http_status_hint=resp.status_code,
                    details={"status_code": resp.status_code},
                )

            if resp.status_code in TRANSIENT_STATUS_CODES:
                self.circuit_breaker.record_failure()
                retry_after = resp.headers.get("Retry-After")
                if attempt < self.max_retries:
                    delay = self._compute_backoff(attempt, retry_after)
                    attempt += 1
                    logger.warning(
                        "Transient upstream HTTP status, retrying",
                        extra={
                            "status_code": resp.status_code,
                            "attempt": attempt,
                            "delay_sec": round(delay, 3),
                        },
                    )
                    await self._sleeper(delay)
                    continue
                if resp.status_code == 429:
                    raise RateLimitError(
                        "Upstream rate limit exceeded after retries",
                        retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
                    )
                raise UpstreamTransientError(
                    f"Upstream transient HTTP {resp.status_code} after {attempt} retries"
                )

            if resp.status_code >= 500:
                self.circuit_breaker.record_failure()
                raise UpstreamTransientError(f"Upstream HTTP {resp.status_code}")

            self.circuit_breaker.record_success()
            return resp
