"""Outbound and inbound Port Protocols (Hexagonal Architecture)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from axisstream_bridge.domain.models import (
    AlertHistoryItem,
    AlertPolicy,
    Asset,
    BatchTelemetryResult,
    Device,
    DeviceTelemetrySnapshot,
    ExchangeTokenInfo,
    FieldLocation,
    Project,
    ProjectForecastBundle,
    ProviderConnection,
    WeatherExchangeRow,
)


class AuthPort(Protocol):
    async def get_auth_headers(self) -> dict[str, str]: ...
    async def get_auth_cookies(self) -> dict[str, str]: ...
    async def refresh_session(self, failed_generation: int) -> None: ...
    @property
    def generation(self) -> int: ...


class MetadataPort(Protocol):
    async def list_projects(self) -> list[Project]: ...
    async def list_devices(self, project_id: str) -> list[Device]: ...
    async def list_fields(self, project_id: str) -> list[FieldLocation]: ...
    async def list_assets(self, project_id: str) -> list[Asset]: ...
    async def list_exchange_tokens(self, project_id: str) -> list[ExchangeTokenInfo]: ...
    async def list_providers(self, project_id: str) -> list[ProviderConnection]: ...


class TelemetryPort(Protocol):
    async def fetch_device_telemetry(
        self,
        org_code: str,
        device: Device,
        start_date: date,
        end_date: date,
        local_timezone: str,
    ) -> DeviceTelemetrySnapshot: ...

    async def fetch_batch_telemetry(
        self,
        org_code: str,
        devices: list[Device],
        start_date: date,
        end_date: date,
        local_timezone: str,
    ) -> BatchTelemetryResult: ...


class AlertPort(Protocol):
    async def list_alert_templates(self) -> list[dict[str, Any]]: ...
    async def list_alert_policies(self, project_id: str) -> list[AlertPolicy]: ...
    async def list_alert_history(self, project_id: str, limit: int = 200) -> list[AlertHistoryItem]: ...


class ExchangePort(Protocol):
    async def fetch_weather_exchange(
        self,
        org_code: str,
        project_id: str,
        limit: int = 15000,
    ) -> list[WeatherExchangeRow]: ...


class StateStorePort(Protocol):
    def get_cursor(self, scope_key: str) -> datetime | None: ...
    def set_cursor(self, scope_key: str, cursor_utc: datetime) -> None: ...
    def check_and_record_dedup(self, dedup_key: str) -> bool: ...
    def enqueue_outbox(self, event_id: str, event_type: str, payload: dict[str, Any]) -> None: ...
    def list_pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]: ...
    def mark_outbox_delivered(self, event_id: str) -> None: ...
    def mark_outbox_failed(self, event_id: str, error: str, max_attempts: int = 3) -> str: ...
    def is_healthy(self) -> bool: ...


class EventPublisherPort(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class ForecastPort(Protocol):
    async def fetch_project_forecast(self, project_id: str) -> ProjectForecastBundle: ...
