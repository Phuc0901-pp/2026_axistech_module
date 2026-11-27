"""Incremental real-time sync orchestrator, SSE event broadcaster, and fail-open consumer."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import logging
from typing import Any
import uuid

from axisstream_bridge.application.demo_provider import DemoAxisStreamProvider
from axisstream_bridge.core.exceptions import AxisStreamError
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
    SyncDeltaEvent,
    WeatherExchangeRow,
)
from axisstream_bridge.infrastructure.storage.state_store import (
    SqliteStateStore,
    compute_dedup_key,
)

logger = logging.getLogger("axisstream_bridge.sync")


class SseEventHub:
    """Thread/async-safe fan-out hub for real-time SSE subscribers."""

    def __init__(self, max_queue_size: int = 100) -> None:
        self._max_queue_size = max_queue_size
        self._subscribers: set[asyncio.Queue[SyncDeltaEvent]] = set()

    def subscribe(self) -> asyncio.Queue[SyncDeltaEvent]:
        q: asyncio.Queue[SyncDeltaEvent] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[SyncDeltaEvent]) -> None:
        self._subscribers.discard(q)

    async def broadcast(self, event: SyncDeltaEvent) -> None:
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


class IncrementalSyncOrchestrator:
    """Coordinates read-only incremental AxisStream synchronization across projects."""

    def __init__(
        self,
        *,
        provider: Any,
        state_store: SqliteStateStore,
        event_hub: SseEventHub,
        local_timezone: str = "Asia/Ho_Chi_Minh",
    ) -> None:
        self._provider = provider
        self._store = state_store
        self._hub = event_hub
        self._local_timezone = local_timezone
        self._cache_projects: list[Project] = []
        self._cache_devices: dict[str, list[Device]] = {}
        self._cache_snapshots: dict[str, list[DeviceTelemetrySnapshot]] = {}
        self._cache_fields: dict[str, list[FieldLocation]] = {}
        self._cache_assets: dict[str, list[Asset]] = {}
        self._cache_policies: dict[str, list[AlertPolicy]] = {}
        self._cache_history: dict[str, list[AlertHistoryItem]] = {}
        self._cache_providers: dict[str, list[ProviderConnection]] = {}
        self._cache_exchange_tokens: dict[str, list[ExchangeTokenInfo]] = {}
        self._cache_exchange_weather: dict[str, list[WeatherExchangeRow]] = {}
        self._cache_forecasts: dict[str, ProjectForecastBundle] = {}
        self._history_hydrated: set[str] = set()
        self._sync_count = 0
        self._last_sync_utc: datetime | None = None
        self._last_error: str = ""

    @property
    def sync_count(self) -> int:
        return self._sync_count

    @property
    def last_sync_utc(self) -> datetime | None:
        return self._last_sync_utc

    @property
    def last_error(self) -> str:
        return self._last_error

    async def sync_all(self) -> dict[str, Any]:
        """Run one full read-only incremental sync cycle.

        Rollback-safe: watermark cursor only advances after outbox/dedup persistence succeeds.
        """
        try:
            res = await self._run_sync_cycle()
            self._last_error = ""
            return res
        except Exception as exc:
            self._last_error = str(exc)
            raise

    async def _run_sync_cycle(self) -> dict[str, Any]:
        if isinstance(self._provider, DemoAxisStreamProvider):
            self._provider.bump_tick()

        projects = await self._provider.list_projects()
        self._cache_projects = projects

        today = datetime.now(timezone.utc).date()
        start_date = today
        total_new_readings = 0
        partial_errors: list[dict[str, Any]] = []

        for proj in projects:
            pid = proj.id
            org_code = proj.organisation.schema_name
            cursor_key = f"telemetry:{pid}"
            prev_cursor = self._store.get_cursor(cursor_key)
            eff_start = prev_cursor.date() if prev_cursor else start_date

            devices = await self._provider.list_devices(pid)
            fields = await self._provider.list_fields(pid)
            assets = await self._provider.list_assets(pid)
            policies = await self._provider.list_alert_policies(pid)
            history = await self._provider.list_alert_history(pid, limit=200)
            providers = await self._provider.list_providers(pid)
            ex_tokens = await self._provider.list_exchange_tokens(pid)
            ex_weather = await self._provider.fetch_weather_exchange(org_code, pid, limit=15000)
            forecast_bundle: ProjectForecastBundle | None = None
            if hasattr(self._provider, "fetch_project_forecast"):
                forecast_bundle = await self._provider.fetch_project_forecast(pid)

            batch: BatchTelemetryResult = await self._provider.fetch_batch_telemetry(
                org_code, devices, eff_start, today, self._local_timezone
            )
            for err in batch.errors:
                partial_errors.append(err.model_dump())

            new_readings_for_proj = 0
            latest_ts_seen: datetime | None = prev_cursor

            for snap in batch.snapshots:
                if snap.latest_timestamp_utc and (
                    latest_ts_seen is None or snap.latest_timestamp_utc > latest_ts_seen
                ):
                    latest_ts_seen = snap.latest_timestamp_utc
                self._store.save_telemetry_readings(pid, snap.readings)
                for reading in snap.readings:
                    dkey = compute_dedup_key(
                        org_code,
                        reading.device_id,
                        reading.metric,
                        reading.timestamp_utc,
                        reading.depth_level,
                    )
                    if self._store.check_and_record_dedup(dkey):
                        new_readings_for_proj += 1

            # Hydrate 24h device history on first sync for historical chart continuity
            if hasattr(self._provider, "fetch_device_history"):
                for dev in devices:
                    if dev.id in self._history_hydrated:
                        continue
                    try:
                        hist_readings = await self._provider.fetch_device_history(pid, dev, hours=24)
                        if hist_readings:
                            self._store.save_telemetry_readings(pid, hist_readings)
                    except Exception as exc:
                        logger.warning(
                            "Device history hydration skipped",
                            extra={"device_id": dev.id, "error": str(exc)},
                        )
                    self._history_hydrated.add(dev.id)

            total_new_readings += new_readings_for_proj

            # Persist outbox event & advance cursor only after successful mapping
            event_id = str(uuid.uuid4())
            event = SyncDeltaEvent(
                event_id=event_id,
                event_type="telemetry_update",
                project_id=pid,
                timestamp_utc=datetime.now(timezone.utc),
                payload={
                    "project_name": proj.name,
                    "device_count": len(devices),
                    "new_readings": new_readings_for_proj,
                    "alert_policies": len(policies),
                    "exchange_rows": len(ex_weather),
                },
            )
            self._store.enqueue_outbox(event_id, event.event_type, event.model_dump(mode="json"))

            if latest_ts_seen is not None:
                self._store.set_cursor(cursor_key, latest_ts_seen)

            self._cache_devices[pid] = devices
            self._cache_snapshots[pid] = batch.snapshots
            self._cache_fields[pid] = fields
            self._cache_assets[pid] = assets
            self._cache_policies[pid] = policies
            self._cache_history[pid] = history
            self._cache_providers[pid] = providers
            self._cache_exchange_tokens[pid] = ex_tokens
            self._cache_exchange_weather[pid] = ex_weather
            if forecast_bundle is not None:
                self._cache_forecasts[pid] = forecast_bundle

            await self._hub.broadcast(event)

        self._sync_count += 1
        self._last_sync_utc = datetime.now(timezone.utc)
        summary = {
            "sync_count": self._sync_count,
            "synced_at_utc": self._last_sync_utc.isoformat(),
            "projects": len(projects),
            "new_readings": total_new_readings,
            "partial_errors": partial_errors,
        }
        await self._hub.broadcast(
            SyncDeltaEvent(
                event_id=str(uuid.uuid4()),
                event_type="sync_complete",
                project_id="ALL",
                timestamp_utc=self._last_sync_utc,
                payload=summary,
            )
        )
        return summary

    def get_projects(self) -> list[Project]:
        return list(self._cache_projects)

    def get_devices(self, project_id: str) -> list[Device]:
        return list(self._cache_devices.get(project_id, []))

    def get_telemetry(self, project_id: str) -> list[DeviceTelemetrySnapshot]:
        return list(self._cache_snapshots.get(project_id, []))

    def get_fields(self, project_id: str) -> list[FieldLocation]:
        return list(self._cache_fields.get(project_id, []))

    def get_assets(self, project_id: str) -> list[Asset]:
        return list(self._cache_assets.get(project_id, []))

    def get_alert_policies(self, project_id: str) -> list[AlertPolicy]:
        return list(self._cache_policies.get(project_id, []))

    def get_alert_history(self, project_id: str) -> list[AlertHistoryItem]:
        return list(self._cache_history.get(project_id, []))

    def get_providers(self, project_id: str) -> list[ProviderConnection]:
        return list(self._cache_providers.get(project_id, []))

    def get_exchange_tokens(self, project_id: str) -> list[ExchangeTokenInfo]:
        return list(self._cache_exchange_tokens.get(project_id, []))

    def get_exchange_weather(self, project_id: str) -> list[WeatherExchangeRow]:
        return list(self._cache_exchange_weather.get(project_id, []))

    def get_forecast(self, project_id: str) -> ProjectForecastBundle | None:
        return self._cache_forecasts.get(project_id)

    def get_telemetry_history(
        self,
        project_id: str,
        *,
        device_id: str | None = None,
        hours: int = 24,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        return self._store.query_telemetry_history(
            project_id, device_id=device_id, hours=hours, limit=limit
        )


class FailOpenEnrichmentConsumer:
    """Reference consumer adapter demonstrating fail-open enrichment for external modules."""

    def __init__(self, orchestrator: IncrementalSyncOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def enrich_record(
        self, project_id: str, external_record: dict[str, Any]
    ) -> dict[str, Any]:
        """Attach latest weather/field context; never block caller if upstream is down."""
        enriched = dict(external_record)
        try:
            snapshots = self._orchestrator.get_telemetry(project_id)
            weather_snap = next((s for s in snapshots if s.source_code == "weather"), None)
            if weather_snap is not None:
                enriched["farm_weather"] = {
                    r.metric: {"value": r.value, "unit": r.unit}
                    for r in weather_snap.readings
                }
            enriched["enrichment_status"] = "OK" if weather_snap else "UNAVAILABLE"
        except (AxisStreamError, Exception):
            enriched["enrichment_status"] = "DEGRADED_FAIL_OPEN"
        return enriched
