"""Cookie-based session authenticator with single-flight async refresh lock."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import httpx

from axisstream_bridge.core.exceptions import AuthenticationError

logger = logging.getLogger("axisstream_bridge.auth")

LoginCallback = Callable[[], Awaitable[dict[str, str]]]


def create_axisstream_login_callback(
    v2_base_url: str,
    email: str,
    password: str,
    *,
    timeout_sec: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LoginCallback:
    """Build live login callback targeting POST /api/account/login on AxisStream."""
    base = v2_base_url.rstrip("/")

    async def _login() -> dict[str, str]:
        if not email.strip() or not password.strip():
            raise AuthenticationError("AxisStream email and password are required for live login")
        async with httpx.AsyncClient(
            verify=True,
            timeout=timeout_sec,
            transport=transport,
        ) as client:
            resp = await client.post(
                f"{base}/api/account/login",
                json={"email": email.strip(), "password": password, "rememberMe": False},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                raise AuthenticationError(
                    f"AxisStream login rejected with HTTP {resp.status_code}"
                )
            try:
                body = resp.json()
            except ValueError:
                body = {}
            if isinstance(body, dict) and body.get("twoFactorAuth") and body.get("idToken"):
                raise AuthenticationError("AxisStream account requires interactive 2FA verification")

            cookies = {k: v for k, v in client.cookies.items()}
            cookies.update({k: v for k, v in resp.cookies.items()})
            if not cookies:
                raise AuthenticationError("AxisStream login succeeded without issuing session cookies")
            return cookies

    return _login


class CookieSessionAuthenticator:
    """Manages AxisStream HQ session cookies with single-flight re-authentication."""

    def __init__(self, login_fn: LoginCallback) -> None:
        self._login_fn = login_fn
        self._cookies: dict[str, str] = {}
        self._generation = 0
        self._lock = asyncio.Lock()

    @property
    def generation(self) -> int:
        return self._generation

    async def get_auth_headers(self) -> dict[str, str]:
        return {}

    async def get_auth_cookies(self) -> dict[str, str]:
        if not self._cookies:
            await self.refresh_session(self._generation)
        return dict(self._cookies)

    async def refresh_session(self, failed_generation: int) -> None:
        """Ensure only one coroutine executes login_fn per failed session generation."""
        async with self._lock:
            if self._generation != failed_generation and self._cookies:
                return
            cookies = await self._login_fn()
            if not cookies:
                raise AuthenticationError("Login callback returned empty session cookies")
            self._cookies = dict(cookies)
            self._generation += 1
            logger.info(
                "Refreshed AxisStream cookie session",
                extra={"session_generation": self._generation},
            )
