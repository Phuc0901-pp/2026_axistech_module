"""Prompt 3 Unit Tests (UT-013 to UT-020): Circuit Breaker, Rate Limiter, HTTP Retry, Dual Auth."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from axisstream_bridge.core.exceptions import (
    AuthenticationError,
    CircuitOpenError,
    RateLimitError,
    SecurityViolationError,
    ValidationError,
)
from axisstream_bridge.infrastructure.auth.cookie_auth import CookieSessionAuthenticator
from axisstream_bridge.infrastructure.auth.exchange_auth import ApiExchangeTokenAuthenticator
from axisstream_bridge.infrastructure.http.circuit_breaker import CircuitBreaker, CircuitState
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from axisstream_bridge.infrastructure.http.rate_limiter import TokenBucketRateLimiter


class FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, sec: float) -> None:
        self.now += sec


def test_ut_013_circuit_breaker_state_transitions() -> None:
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=10.0, clock=clock)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True

    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False

    clock.advance(10.0)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True
    assert cb.allow_request() is False  # only 1 probe allowed

    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    clock.advance(10.0)
    assert cb.allow_request() is True
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


async def test_ut_014_rate_limiter_deterministic_throttling() -> None:
    clock = FakeClock(0.0)
    slept: list[float] = []

    async def fake_sleep(sec: float) -> None:
        slept.append(sec)
        clock.advance(sec)

    limiter = TokenBucketRateLimiter(rate_per_sec=2.0, burst=2, clock=clock, sleeper=fake_sleep)
    assert await limiter.acquire() == 0.0
    assert await limiter.acquire() == 0.0
    waited = await limiter.acquire()
    assert waited == pytest.approx(0.5)
    assert slept == [pytest.approx(0.5)]


@respx.mock
async def test_ut_015_retry_transient_respects_retry_after_and_skips_4xx() -> None:
    slept: list[float] = []

    async def fake_sleep(sec: float) -> None:
        slept.append(sec)

    route = respx.get("https://v2.api.axisstream.co/api/test").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    client = ResilientHttpClient(
        max_retries=3,
        base_backoff_sec=0.1,
        sleeper=fake_sleep,
        jitter_fn=lambda a, b: b,
    )
    try:
        res = await client.request_json("GET", "https://v2.api.axisstream.co/api/test")
        assert res == {"ok": True}
        assert route.call_count == 3
        assert slept == [0.1, 2.0]

        respx.get("https://v2.api.axisstream.co/api/bad").mock(return_value=httpx.Response(404))
        with pytest.raises(ValidationError):
            await client.request_json("GET", "https://v2.api.axisstream.co/api/bad")
    finally:
        await client.aclose()


@respx.mock
async def test_ut_016_concurrent_401_triggers_single_flight_reauth() -> None:
    login_calls = 0

    async def fake_login() -> dict[str, str]:
        nonlocal login_calls
        login_calls += 1
        await asyncio.sleep(0.01)
        return {"sid": f"session-{login_calls}"}

    auth = CookieSessionAuthenticator(fake_login)
    await auth.refresh_session(0)
    assert login_calls == 1

    def responder(request: httpx.Request) -> httpx.Response:
        if "sid=session-1" in request.headers.get("cookie", ""):
            return httpx.Response(401)
        return httpx.Response(200, json={"ok": True})

    respx.get("https://v2.api.axisstream.co/api/data").mock(side_effect=responder)
    client = ResilientHttpClient(auth=auth)
    try:
        results = await asyncio.gather(
            *[client.request_json("GET", "https://v2.api.axisstream.co/api/data") for _ in range(10)]
        )
        assert len(results) == 10
        assert all(r == {"ok": True} for r in results)
        assert login_calls == 2  # initial + exactly 1 re-login for all 10 concurrent 401s
    finally:
        await client.aclose()


@respx.mock
async def test_ut_017_prevent_infinite_401_reauth_loop() -> None:
    login_calls = 0

    async def fake_login() -> dict[str, str]:
        nonlocal login_calls
        login_calls += 1
        return {"sid": f"bad-{login_calls}"}

    auth = CookieSessionAuthenticator(fake_login)
    respx.get("https://v2.api.axisstream.co/api/always401").mock(return_value=httpx.Response(401))
    client = ResilientHttpClient(auth=auth)
    try:
        with pytest.raises(AuthenticationError):
            await client.request_json("GET", "https://v2.api.axisstream.co/api/always401")
        assert login_calls == 2  # initial get_auth_cookies + 1 retry
    finally:
        await client.aclose()


@respx.mock
async def test_ut_018_tls_and_redirect_host_whitelist_guard() -> None:
    client = ResilientHttpClient(allowed_host_suffix=".axisstream.co")
    try:
        with pytest.raises(SecurityViolationError):
            await client.request_json("GET", "http://v2.api.axisstream.co/api/project/list")
        with pytest.raises(SecurityViolationError):
            await client.request_json("GET", "https://attacker.example.com/steal")

        respx.get("https://v2.api.axisstream.co/api/redir").mock(
            return_value=httpx.Response(302, headers={"Location": "https://evil.example.org/phish"})
        )
        with pytest.raises(SecurityViolationError):
            await client.request_json("GET", "https://v2.api.axisstream.co/api/redir")
    finally:
        await client.aclose()


async def test_ut_019_exchange_token_expiry_checks(caplog: pytest.LogCaptureFixture) -> None:
    now = datetime(2026, 11, 26, tzinfo=timezone.utc)
    auth_ok = ApiExchangeTokenAuthenticator(
        "tok_valid", valid_until=now + timedelta(days=10), now_fn=lambda: now
    )
    headers = await auth_ok.get_auth_headers()
    assert headers["X-API-Key"] == "tok_valid"

    auth_expired = ApiExchangeTokenAuthenticator(
        "tok_old", valid_until=now - timedelta(days=1), now_fn=lambda: now
    )
    with pytest.raises(AuthenticationError, match="expired"):
        await auth_expired.get_auth_headers()


@respx.mock
async def test_ut_020_no_credential_leakage_on_http_error(caplog: pytest.LogCaptureFixture) -> None:
    async def fake_login() -> dict[str, str]:
        return {"sid": "TOP_SECRET_COOKIE_999"}

    auth = CookieSessionAuthenticator(fake_login)
    respx.get("https://v2.api.axisstream.co/api/fail").mock(return_value=httpx.Response(503))

    async def no_sleep(_: float) -> None:
        return None

    client = ResilientHttpClient(auth=auth, max_retries=1, sleeper=no_sleep)
    try:
        with pytest.raises(Exception) as exc_info:
            await client.request_json("GET", "https://v2.api.axisstream.co/api/fail")
        assert "TOP_SECRET_COOKIE_999" not in str(exc_info.value)
        assert "TOP_SECRET_COOKIE_999" not in caplog.text
    finally:
        await client.aclose()
