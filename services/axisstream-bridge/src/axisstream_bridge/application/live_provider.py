"""Live AxisStream data provider wired to v2.api, data.api, and provider.api."""

from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Any

from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import AxisStreamError
from axisstream_bridge.domain.models import (
    AlertHistoryItem,
    AlertPolicy,
    Asset,
    BatchTelemetryResult,
    Device,
    ExchangeTokenInfo,
    FieldLocation,
    Project,
    ProjectForecastBundle,
    ProviderConnection,
    WeatherExchangeRow,
    WeatherForecastReport,
)
from axisstream_bridge.infrastructure.auth.cookie_auth import (
    CookieSessionAuthenticator,
    create_axisstream_login_callback,
)
from axisstream_bridge.infrastructure.auth.exchange_auth import (
    ApiExchangeTokenAuthenticator,
)
from axisstream_bridge.infrastructure.axisstream.alert_client import (
    AxisStreamAlertClient,
    AxisStreamExchangeClient,
)
from axisstream_bridge.infrastructure.axisstream.forecast_client import (
    AxisStreamForecastClient,
)
from axisstream_bridge.infrastructure.axisstream.telemetry_client import (
    AxisStreamTelemetryClient,
)
from axisstream_bridge.infrastructure.axisstream.v2_client import AxisStreamV2Client
from axisstream_bridge.infrastructure.http.circuit_breaker import CircuitBreaker
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from axisstream_bridge.infrastructure.http.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("axisstream_bridge.live")

DEFAULT_METNORWAY_PROVIDER_ID = "4c052fb9-d254-4f3e-9b2d-1ab64b86e91c"


class LiveAxisStreamProvider:
    """Real-time read-only provider pulling live data from *.axisstream.co."""

    def __init__(
        self,
        settings: BridgeSettings,
        *,
        http_client: ResilientHttpClient | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings = settings
        self._owns_http = http_client is None
        if http_client is not None:
            self._http = http_client
        else:
            login_cb = create_axisstream_login_callback(
                settings.v2_base_url,
                settings.axisstream_username,
                settings.axisstream_password.get_secret_value(),
                timeout_sec=settings.request_timeout_sec,
            )
            auth = CookieSessionAuthenticator(login_cb)
            self._http = ResilientHttpClient(
                allowed_host_suffix=settings.allowed_host_suffix,
                timeout_sec=settings.request_timeout_sec,
                max_retries=settings.max_retries,
                circuit_breaker=circuit_breaker
                or CircuitBreaker(
                    failure_threshold=settings.circuit_failure_threshold,
                    recovery_timeout_sec=settings.circuit_recovery_sec,
                ),
                rate_limiter=TokenBucketRateLimiter(
                    rate_per_sec=settings.rate_limit_rps,
                    burst=settings.rate_limit_burst,
                ),
                auth=auth,
            )

        self._exchange_http: ResilientHttpClient | None = None
        if http_client is None and settings.auth_mode in ("exchange_token", "dual"):
            ex_tok = settings.axisstream_exchange_token.get_secret_value().strip()
            if ex_tok:
                ex_auth = ApiExchangeTokenAuthenticator(ex_tok)
                self._exchange_http = ResilientHttpClient(
                    allowed_host_suffix=settings.allowed_host_suffix,
                    timeout_sec=settings.request_timeout_sec,
                    max_retries=settings.max_retries,
                    circuit_breaker=circuit_breaker
                    or CircuitBreaker(
                        failure_threshold=settings.circuit_failure_threshold,
                        recovery_timeout_sec=settings.circuit_recovery_sec,
                    ),
                    rate_limiter=TokenBucketRateLimiter(
                        rate_per_sec=settings.rate_limit_rps,
                        burst=settings.rate_limit_burst,
                    ),
                    auth=ex_auth,
                )

        self._v2 = AxisStreamV2Client(self._http, base_url=settings.v2_base_url)
        self._telemetry = AxisStreamTelemetryClient(self._http, base_url=settings.data_base_url)
        self._alerts = AxisStreamAlertClient(
            self._http,
            v2_base_url=settings.v2_base_url,
            provider_base_url=settings.provider_base_url,
        )
        self._exchange = AxisStreamExchangeClient(
            self._exchange_http or self._http, data_base_url=settings.data_base_url
        )
        self._forecast = AxisStreamForecastClient(
            self._http, provider_base_url=settings.provider_base_url
        )
        self._provider_cache: dict[str, list[ProviderConnection]] = {}

    async def aclose(self) -> None:
        if self._exchange_http is not None:
            await self._exchange_http.aclose()
        if self._owns_http:
            await self._http.aclose()

    async def list_projects(self) -> list[Project]:
        return await self._v2.list_projects()

    async def list_devices(self, project_id: str) -> list[Device]:
        return await self._v2.list_devices(project_id)

    async def list_fields(self, project_id: str) -> list[FieldLocation]:
        try:
            return await self._v2.list_fields(project_id)
        except AxisStreamError as exc:
            logger.warning("Fields fetch degraded", extra={"project_id": project_id, "error": exc.code})
            return []

    async def list_assets(self, project_id: str) -> list[Asset]:
        try:
            return await self._v2.list_assets(project_id)
        except AxisStreamError as exc:
            logger.warning("Assets fetch degraded", extra={"project_id": project_id, "error": exc.code})
            return []

    async def list_alert_policies(self, project_id: str) -> list[AlertPolicy]:
        try:
            return await self._alerts.list_alert_policies(project_id)
        except AxisStreamError as exc:
            logger.warning("Alert policies fetch degraded", extra={"project_id": project_id, "error": exc.code})
            return []

    async def list_alert_history(self, project_id: str, limit: int = 200) -> list[AlertHistoryItem]:
        try:
            return await self._alerts.list_alert_history(project_id, limit=limit)
        except AxisStreamError as exc:
            logger.warning("Alert history fetch degraded", extra={"project_id": project_id, "error": exc.code})
            return []

    async def list_providers(self, project_id: str) -> list[ProviderConnection]:
        providers = await self._v2.list_providers(project_id)
        self._provider_cache[project_id] = providers
        return providers

    async def list_exchange_tokens(self, project_id: str) -> list[ExchangeTokenInfo]:
        try:
            return await self._v2.list_exchange_tokens(project_id)
        except AxisStreamError as exc:
            logger.warning("Exchange tokens fetch degraded", extra={"project_id": project_id, "error": exc.code})
            return []

    async def fetch_batch_telemetry(
        self,
        org_code: str,
        devices: list[Device],
        start_date: date,
        end_date: date,
        local_timezone: str = "Asia/Ho_Chi_Minh",
    ) -> BatchTelemetryResult:
        if not devices:
            return BatchTelemetryResult()
        try:
            res = await self._telemetry.fetch_batch_telemetry(
                org_code, devices, start_date, end_date, local_timezone
            )
            if res.snapshots:
                return res
        except AxisStreamError as exc:
            logger.warning("Batch telemetry failed; falling back to per-device queries", extra={"error": exc.code})

        snapshots = []
        errors = []
        for dev in devices:
            try:
                snap = await self._telemetry.fetch_device_telemetry(
                    org_code, dev, start_date, end_date, local_timezone
                )
                snapshots.append(snap)
            except AxisStreamError as exc:
                from axisstream_bridge.domain.models import PartialError
                errors.append(
                    PartialError(
                        target_id=dev.external_id,
                        endpoint=f"{dev.source_code}/{dev.external_id}",
                        status_code=exc.http_status_hint,
                        message=str(exc),
                    )
                )
        return BatchTelemetryResult(snapshots=snapshots, errors=errors)

    async def fetch_weather_exchange(
        self, org_code: str, project_id: str, limit: int = 15000
    ) -> list[WeatherExchangeRow]:
        try:
            rows = await self._exchange.fetch_weather_exchange(org_code, project_id, limit=limit)
            if rows:
                return rows
        except AxisStreamError:
            pass

        # Fallback: derive normalized WeatherExchangeRow from live weather device snapshot
        try:
            devices = await self._v2.list_devices(project_id)
            weather_devs = [d for d in devices if d.source_code == "weather"]
            if not weather_devs:
                return []
            today = datetime.now(timezone.utc).date()
            snap = await self._telemetry.fetch_device_telemetry(
                org_code, weather_devs[0], today, today, self._settings.local_timezone
            )
            if not snap.readings:
                return []
            m = {r.metric: r.value for r in snap.readings}
            ts = snap.latest_timestamp_utc or snap.readings[0].timestamp_utc
            return [
                WeatherExchangeRow(
                    code=weather_devs[0].external_id,
                    time=ts,
                    temperature_avg=m.get("temperature"),
                    humidity_avg=m.get("humidity"),
                    deltat_avg=m.get("delta_t"),
                    dewpoint_avg=m.get("dew_point"),
                    atmos_pressure_avg=m.get("atmos_pressure"),
                    msl_pressure=m.get("msl_pressure"),
                    rainfall=m.get("rainfall") or m.get("rainfall_last_24hrs"),
                    rainfall_total=m.get("rainfall_last_24hrs") or m.get("rainfall_total"),
                    wind_speed_avg=m.get("wind_speed"),
                    wind_speed_max=m.get("wind_gust"),
                    wind_dir_deg_avg=m.get("wind_direction"),
                    solar_rad_avg=m.get("solar_radiation"),
                    uv_index_avg=m.get("uv_index"),
                )
            ]
        except AxisStreamError:
            return []

    async def fetch_project_forecast(self, project_id: str) -> ProjectForecastBundle:
        providers = self._provider_cache.get(project_id)
        if providers is None:
            providers = await self.list_providers(project_id)

        met_id = self._settings.metnorway_provider_id.strip()
        janes_id = self._settings.janes_weather_provider_id.strip()
        for p in providers:
            key = f"{p.code} {p.name}".lower()
            if not met_id and ("met" in key or "norway" in key):
                met_id = p.id
            if not janes_id and "jane" in key:
                janes_id = p.id

        if not met_id:
            met_id = DEFAULT_METNORWAY_PROVIDER_ID

        met_report = await self._forecast.fetch_metnorway_forecast(project_id, met_id)
        janes_report = (
            await self._forecast.fetch_janes_forecast(project_id, janes_id)
            if janes_id
            else WeatherForecastReport(provider="Jane's Weather", status="DISCONNECTED")
        )
        return ProjectForecastBundle(
            project_id=project_id,
            met_norway=met_report,
            janes_weather=janes_report,
        )
