"""ISO/IEC 27001 compliant configuration management using Pydantic v2 SecretStr."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BridgeSettings(BaseSettings):
    """Configuration for the AxisStream integration bridge.

    Secrets are wrapped in SecretStr and all upstream URLs must use HTTPS
    targeting the configured allowed host suffix.
    """

    model_config = SettingsConfigDict(
        env_prefix="AXISSTREAM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    mode: Literal["demo", "live"] = "demo"
    auth_mode: Literal["cookie", "exchange_token", "dual"] = "dual"

    v2_base_url: str = "https://v2.api.axisstream.co"
    data_base_url: str = "https://data.api.axisstream.co"
    provider_base_url: str = "https://provider.api.axisstream.co"
    allowed_host_suffix: str = ".axisstream.co"

    axisstream_username: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AXISSTREAM_EMAIL",
            "AXISSTREAM_USERNAME",
            "AXISSTREAM_AXISSTREAM_USERNAME",
        ),
    )
    axisstream_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "AXISSTREAM_PASSWORD",
            "AXISSTREAM_AXISSTREAM_PASSWORD",
        ),
    )
    axisstream_exchange_token: SecretStr = SecretStr("")
    metnorway_provider_id: str = ""
    janes_weather_provider_id: str = ""
    inbound_api_key: SecretStr = SecretStr("dev-bridge-api-key-change-me")
    webhook_secret: SecretStr = SecretStr("dev-webhook-secret-change-me")
    webhook_url: str = ""

    sync_interval_sec: float = Field(default=15.0, ge=0.5, le=3600.0)
    request_timeout_sec: float = Field(default=15.0, ge=1.0, le=120.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    circuit_failure_threshold: int = Field(default=5, ge=1, le=50)
    circuit_recovery_sec: float = Field(default=30.0, ge=1.0, le=600.0)
    rate_limit_rps: float = Field(default=10.0, gt=0.0, le=500.0)
    rate_limit_burst: int = Field(default=20, ge=1, le=1000)

    sqlite_path: str = ":memory:"
    database_url: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("database_url", "AXISSTREAM_DATABASE_URL", "DATABASE_URL"),
    )
    local_timezone: str = "Asia/Ho_Chi_Minh"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ISO 27001 AEAD at-rest encryption key for SQLite outbox payloads
    encryption_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("encryption_key", "AXISSTREAM_ENCRYPTION_KEY", "BRIDGE_ENCRYPTION_KEY"),
    )

    @field_validator("v2_base_url", "data_base_url", "provider_base_url")
    @classmethod
    def _validate_https_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme.lower() != "https":
            raise ValueError(f"Upstream URL must use https:// scheme, got: {value!r}")
        if not parsed.netloc:
            raise ValueError(f"Upstream URL missing host: {value!r}")
        return value.rstrip("/")

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        parsed = urlparse(cleaned)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid webhook_url: {value!r}")
        return cleaned

    @model_validator(mode="after")
    def _validate_live_credentials_and_hosts(self) -> "BridgeSettings":
        suffix = self.allowed_host_suffix.lower().lstrip("*")
        for field_name in ("v2_base_url", "data_base_url", "provider_base_url"):
            url = getattr(self, field_name)
            host = (urlparse(url).hostname or "").lower()
            if suffix and not (host == suffix.lstrip(".") or host.endswith(suffix)):
                raise ValueError(
                    f"{field_name} host {host!r} is not under allowed suffix {self.allowed_host_suffix!r}"
                )

        if self.mode == "live":
            has_cookie_creds = bool(
                self.axisstream_username.strip()
                and self.axisstream_password.get_secret_value().strip()
            )
            has_exchange_token = bool(
                self.axisstream_exchange_token.get_secret_value().strip()
            )
            if self.auth_mode == "cookie" and not has_cookie_creds:
                raise ValueError(
                    "Live mode with auth_mode='cookie' requires username and password"
                )
            if self.auth_mode == "exchange_token" and not has_exchange_token:
                raise ValueError(
                    "Live mode with auth_mode='exchange_token' requires exchange token"
                )
            if self.auth_mode == "dual" and not (has_cookie_creds or has_exchange_token):
                raise ValueError(
                    "Live mode with auth_mode='dual' requires cookie credentials or exchange token"
                )

        return self

    def __repr__(self) -> str:
        return (
            f"BridgeSettings(mode={self.mode!r}, auth_mode={self.auth_mode!r}, "
            f"v2_base_url={self.v2_base_url!r}, data_base_url={self.data_base_url!r}, "
            f"provider_base_url={self.provider_base_url!r}, "
            f"axisstream_password='**********', axisstream_exchange_token='**********', "
            f"encryption_key='**********', inbound_api_key='**********', webhook_secret='**********')"
        )
