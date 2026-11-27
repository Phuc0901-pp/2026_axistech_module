"""API Exchange scoped token authenticator with expiry guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from axisstream_bridge.core.exceptions import AuthenticationError
from axisstream_bridge.domain.normalizers import parse_iso_timestamp

logger = logging.getLogger("axisstream_bridge.auth")


class ApiExchangeTokenAuthenticator:
    """Validates and supplies AxisStream API Exchange tokens without leaking secrets."""

    def __init__(
        self,
        token: str,
        *,
        valid_until: str | datetime | None = None,
        warn_days_before_expiry: int = 30,
        now_fn: callable | None = None,
    ) -> None:
        self._token = token.strip()
        self._valid_until = (
            parse_iso_timestamp(valid_until) if valid_until is not None else None
        )
        self._warn_days = warn_days_before_expiry
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._generation = 1

    @property
    def generation(self) -> int:
        return self._generation

    def validate_token_status(self) -> None:
        if not self._token:
            raise AuthenticationError("API Exchange token is empty")
        if self._valid_until is not None:
            now = self._now_fn()
            if now >= self._valid_until:
                raise AuthenticationError("API Exchange token has expired")
            if (self._valid_until - now) <= timedelta(days=self._warn_days):
                logger.warning(
                    "API Exchange token is nearing expiry",
                    extra={"valid_until_utc": self._valid_until.isoformat()},
                )

    async def get_auth_headers(self) -> dict[str, str]:
        self.validate_token_status()
        return {"X-API-Key": self._token}

    async def get_auth_cookies(self) -> dict[str, str]:
        return {}

    async def refresh_session(self, failed_generation: int) -> None:
        raise AuthenticationError(
            "Static API Exchange token rejected (401); manual token rotation required"
        )
