"""AxisStream data.api.axisstream.co Telemetry client with Strategy Mappers & Partial Failure Isolation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from axisstream_bridge.core.exceptions import AxisStreamError, ValidationError
from axisstream_bridge.domain.models import (
    BatchTelemetryResult,
    Device,
    DeviceMetadata,
    DeviceTelemetrySnapshot,
    PartialError,
    TelemetryReading,
)
from axisstream_bridge.domain.normalizers import (
    normalize_unit,
    parse_iso_timestamp,
    parse_numeric,
    validate_safe_path_segment,
)
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient

logger = logging.getLogger("axisstream_bridge.acl.telemetry")


def chunk_date_range(
    start_date: date, end_date: date, *, max_days: int = 30
) -> list[tuple[date, date]]:
    """Split large date ranges into inclusive non-overlapping chunks."""
    if start_date > end_date:
        raise ValidationError(
            f"start_date ({start_date}) must be <= end_date ({end_date})"
        )
    if max_days < 1:
        raise ValidationError("max_days must be >= 1")
    chunks: list[tuple[date, date]] = []
    cur = start_date
    step = timedelta(days=max_days - 1)
    while cur <= end_date:
        chunk_end = min(end_date, cur + step)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _extract_common(
    device: Device, body: dict[str, Any]
) -> tuple[DeviceMetadata, datetime | None, datetime | None, dict[str, str]]:
    meta_raw = body.get("metadata") or {}
    time_seg = body.get("timeSegments") or {}
    raw_uom = body.get("uom") or {}
    uom = {str(k): normalize_unit(str(v)) for k, v in raw_uom.items()}

    latest_ts = parse_iso_timestamp(time_seg.get("latestDate")) or parse_iso_timestamp(
        meta_raw.get("time")
    )
    earliest_ts = parse_iso_timestamp(time_seg.get("earliestDate"))
    metadata = DeviceMetadata(
        last_reported_utc=parse_iso_timestamp(meta_raw.get("time")),
        battery_level=parse_numeric(meta_raw.get("batteryLevel")),
        signal_strength_dbm=parse_numeric(meta_raw.get("signalStrength")),
        reading_interval=meta_raw.get("readingInterval"),
    )
    return metadata, latest_ts, earliest_ts, uom


def _derive_status(
    device: Device,
    recent_data: dict[str, Any],
    latest_ts: datetime | None,
    body: dict[str, Any] | None = None,
) -> str:
    if not device.active:
        return "OFFLINE"
    if isinstance(body, dict):
        meta = body.get("metadata") or {}
        if body.get("isOnline") is False or body.get("online") is False or meta.get("online") is False or meta.get("isOnline") is False:
            return "OFFLINE"
        if str(body.get("status") or "").strip().lower() in {"offline", "off", "inactive", "disabled"}:
            return "OFFLINE"
    if not recent_data and latest_ts is None:
        return "NO_DATA"
    return "LIVE"


class BaseTelemetryMapper:
    """Base strategy mapper for AxisStream device telemetry payloads."""

    def map_payload(
        self, device: Device, body: dict[str, Any], *, fallback_ts: datetime | None = None
    ) -> DeviceTelemetrySnapshot:
        metadata, latest_ts, earliest_ts, uom = _extract_common(device, body)
        recent = body.get("recentData") or {}
        if not isinstance(recent, dict):
            recent = {}

        sample_ts = (
            parse_iso_timestamp(recent.get("time"))
            or latest_ts
            or metadata.last_reported_utc
            or fallback_ts
        )
        status = _derive_status(device, recent, latest_ts, body)
        readings: list[TelemetryReading] = []

        if sample_ts is not None:
            for key, val in recent.items():
                if key in ("time", "sensor"):
                    continue
                if isinstance(val, dict):
                    continue
                num = parse_numeric(val)
                if num is None:
                    continue
                unit = uom.get(f"recentData.{key}", uom.get(f"timeSeriesData.{key}", ""))
                readings.append(
                    TelemetryReading(
                        device_id=device.id,
                        external_id=device.external_id,
                        source_code=device.source_code,
                        metric=str(key),
                        value=num,
                        unit=unit,
                        timestamp_utc=sample_ts,
                    )
                )

        return DeviceTelemetrySnapshot(
            device_id=device.id,
            external_id=device.external_id,
            source_code=device.source_code,
            status=status,  # type: ignore[arg-type]
            latest_timestamp_utc=latest_ts,
            earliest_timestamp_utc=earliest_ts,
            readings=readings,
            metadata=metadata,
            uom=uom,
        )


class SoilProbeTelemetryMapper(BaseTelemetryMapper):
    """Maps multi-depth soil probe telemetry and reconciles `moist` -> `moisture`."""

    def map_payload(
        self, device: Device, body: dict[str, Any], *, fallback_ts: datetime | None = None
    ) -> DeviceTelemetrySnapshot:
        metadata, latest_ts, earliest_ts, uom = _extract_common(device, body)
        recent = body.get("recentData") or {}
        sample_ts = (
            parse_iso_timestamp(recent.get("time"))
            or latest_ts
            or metadata.last_reported_utc
            or fallback_ts
        )
        status = _derive_status(device, recent, latest_ts, body)
        readings: list[TelemetryReading] = []

        if sample_ts is not None and isinstance(recent, dict):
            for depth_key, depth_metrics in recent.items():
                if depth_key == "time" or not isinstance(depth_metrics, dict):
                    continue
                try:
                    depth_level = int(depth_key)
                except ValueError:
                    continue
                for raw_metric, raw_val in depth_metrics.items():
                    metric_name = "moisture" if raw_metric == "moist" else str(raw_metric)
                    num = parse_numeric(raw_val)
                    if num is None:
                        continue
                    unit = uom.get(
                        f"recentData.{depth_level}.{metric_name}",
                        uom.get(f"timeSeriesData.{metric_name}", ""),
                    )
                    readings.append(
                        TelemetryReading(
                            device_id=device.id,
                            external_id=device.external_id,
                            source_code=device.source_code,
                            metric=metric_name,
                            value=num,
                            unit=unit,
                            depth_level=depth_level,
                            timestamp_utc=sample_ts,
                        )
                    )

        return DeviceTelemetrySnapshot(
            device_id=device.id,
            external_id=device.external_id,
            source_code=device.source_code,
            status=status,  # type: ignore[arg-type]
            latest_timestamp_utc=latest_ts,
            earliest_timestamp_utc=earliest_ts,
            readings=readings,
            metadata=metadata,
            uom=uom,
        )


class WaterLevelTelemetryMapper(BaseTelemetryMapper):
    """Handles tank level sensors including NO_DATA empty recentData & epoch sentinel."""


class WaterFlowTelemetryMapper(BaseTelemetryMapper):
    """Maps Hunter/flow meter telemetry (waterVolume, cumulativeWater, battery)."""


class WeatherTelemetryMapper(BaseTelemetryMapper):
    """Maps weather station telemetry (camelCase & snake_case + summaryData rainfall)."""

    _KEY_ALIASES = {
        "temperature": "temperature",
        "humidity": "humidity",
        "rainfall": "rainfall",
        "rainfallTotal": "rainfall_total",
        "atmosPressure": "atmos_pressure",
        "atmos_pressure": "atmos_pressure",
        "mslPressure": "msl_pressure",
        "msl_pressure": "msl_pressure",
        "deltaT": "delta_t",
        "delta_t": "delta_t",
        "dewPoint": "dew_point",
        "dew_point": "dew_point",
        "windSpeed": "wind_speed",
        "wind_speed": "wind_speed",
        "windDirection": "wind_direction",
        "wind_direction": "wind_direction",
        "windGust": "wind_gust",
        "wind_gust": "wind_gust",
        "solarRadiation": "solar_radiation",
        "solar_radiation": "solar_radiation",
        "uvIndex": "uv_index",
        "uv_index": "uv_index",
        "apparent_temperature_avg": "apparent_temperature_avg",
        "vapour_pressure_deficit": "vapour_pressure_deficit",
        "vapour_pressure": "vapour_pressure",
    }

    _CARDINAL_DEGREES = {
        "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
        "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
        "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
        "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
    }

    def map_payload(
        self, device: Device, body: dict[str, Any], *, fallback_ts: datetime | None = None
    ) -> DeviceTelemetrySnapshot:
        metadata, latest_ts, earliest_ts, uom = _extract_common(device, body)
        recent = body.get("recentData") or {}
        if not isinstance(recent, dict):
            recent = {}

        sample_ts = (
            parse_iso_timestamp(recent.get("time"))
            or latest_ts
            or metadata.last_reported_utc
            or fallback_ts
        )
        status = _derive_status(device, recent, latest_ts, body)
        readings: list[TelemetryReading] = []

        if sample_ts is not None:
            seen_metrics: set[str] = set()
            for raw_key, val in recent.items():
                if raw_key in ("time", "sensor") or isinstance(val, dict):
                    continue
                canonical_metric = self._KEY_ALIASES.get(raw_key, str(raw_key))
                if canonical_metric in seen_metrics:
                    continue
                if canonical_metric == "wind_direction" and isinstance(val, str):
                    num = self._CARDINAL_DEGREES.get(val.strip().upper())
                    if num is None:
                        num = parse_numeric(val)
                else:
                    num = parse_numeric(val)
                if num is None:
                    continue
                seen_metrics.add(canonical_metric)
                unit = uom.get(
                    f"recentData.{raw_key}",
                    uom.get(f"recentData.{canonical_metric}", uom.get(f"timeSeriesData.{raw_key}", "")),
                )
                if canonical_metric == "wind_direction" and not unit:
                    unit = "deg"
                if canonical_metric == "uv_index" and not unit:
                    unit = "index"
                readings.append(
                    TelemetryReading(
                        device_id=device.id,
                        external_id=device.external_id,
                        source_code=device.source_code,
                        metric=canonical_metric,
                        value=num,
                        unit=unit,
                        timestamp_utc=sample_ts,
                    )
                )

            summary = body.get("summaryData") or {}
            rain_summary = summary.get("rainfall") if isinstance(summary, dict) else None
            if isinstance(rain_summary, dict):
                r24 = parse_numeric(rain_summary.get("rainfallLast24hrs"))
                if r24 is not None:
                    readings.append(
                        TelemetryReading(
                            device_id=device.id,
                            external_id=device.external_id,
                            source_code=device.source_code,
                            metric="rainfall_last_24hrs",
                            value=r24,
                            unit=uom.get("summaryData.rainfall.rainfallLast24hrs", "mm"),
                            timestamp_utc=sample_ts,
                        )
                    )

        return DeviceTelemetrySnapshot(
            device_id=device.id,
            external_id=device.external_id,
            source_code=device.source_code,
            status=status,  # type: ignore[arg-type]
            latest_timestamp_utc=latest_ts,
            earliest_timestamp_utc=earliest_ts,
            readings=readings,
            metadata=metadata,
            uom=uom,
        )


class GenericTelemetryMapper(BaseTelemetryMapper):
    """Forward-compatible fallback mapper for new device sourceCodes."""


TELEMETRY_MAPPERS: dict[str, BaseTelemetryMapper] = {
    "weather": WeatherTelemetryMapper(),
    "soilprobe": SoilProbeTelemetryMapper(),
    "waterlevel": WaterLevelTelemetryMapper(),
    "waterflow": WaterFlowTelemetryMapper(),
}


class AxisStreamTelemetryClient:
    """Adapter implementing TelemetryPort against data.api.axisstream.co."""

    def __init__(self, http: ResilientHttpClient, base_url: str = "https://data.api.axisstream.co") -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    def _get_mapper(self, source_code: str) -> BaseTelemetryMapper:
        return TELEMETRY_MAPPERS.get(source_code.lower(), GenericTelemetryMapper())

    async def fetch_device_telemetry(
        self,
        org_code: str,
        device: Device,
        start_date: date,
        end_date: date,
        local_timezone: str = "Asia/Ho_Chi_Minh",
    ) -> DeviceTelemetrySnapshot:
        org = validate_safe_path_segment(org_code, "org_code")
        src = validate_safe_path_segment(device.source_code, "source_code")
        ext = validate_safe_path_segment(device.external_id, "external_id")

        chunks = chunk_date_range(start_date, end_date, max_days=30)
        last_snapshot: DeviceTelemetrySnapshot | None = None
        all_readings: list[TelemetryReading] = []

        for c_start, c_end in chunks:
            url = f"{self._base_url}/device/{org}/{src}/{ext}/device"
            body = await self._http.request_json(
                "GET",
                url,
                params={
                    "startDate": c_start.isoformat(),
                    "endDate": c_end.isoformat(),
                    "localTimeZone": local_timezone,
                },
            )
            snap = self._get_mapper(src).map_payload(device, body or {})
            last_snapshot = snap
            all_readings.extend(snap.readings)

        assert last_snapshot is not None
        return last_snapshot.model_copy(update={"readings": all_readings})

    async def fetch_weather_derived_optional(
        self, org_code: str, external_id: str, derived_type: str
    ) -> dict[str, Any] | None:
        """Fetch optional derived weather endpoints (`weather_eto`, `weather_indices`), returning None on 404/5xx."""
        org = validate_safe_path_segment(org_code, "org_code")
        ext = validate_safe_path_segment(external_id, "external_id")
        dtype = validate_safe_path_segment(derived_type, "derived_type")
        try:
            res = await self._http.request_json(
                "GET", f"{self._base_url}/device/{org}/{dtype}/{ext}/device"
            )
            return res if isinstance(res, dict) else None
        except AxisStreamError as exc:
            logger.warning(
                "Optional derived weather endpoint degraded",
                extra={"derived_type": dtype, "error_code": exc.code},
            )
            return None

    async def fetch_batch_telemetry(
        self,
        org_code: str,
        devices: list[Device],
        start_date: date,
        end_date: date,
        local_timezone: str = "Asia/Ho_Chi_Minh",
    ) -> BatchTelemetryResult:
        """Query batch telemetry and isolate partial per-device failures."""
        if not devices:
            return BatchTelemetryResult()
        org = validate_safe_path_segment(org_code, "org_code")
        url = f"{self._base_url}/device/{org}/batch"
        request_items = [
            {
                "source": validate_safe_path_segment(d.source_code, "source_code"),
                "deviceId": validate_safe_path_segment(d.external_id, "external_id"),
                "uom": d.preferred_uom or "metric",
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "localTimeZone": local_timezone,
            }
            for d in devices
        ]
        payload = await self._http.request_json("POST", url, json_body={"items": request_items})
        results = (payload or {}).get("results", [])

        snapshots: list[DeviceTelemetrySnapshot] = []
        errors: list[PartialError] = []

        for idx, device in enumerate(devices):
            if idx >= len(results):
                errors.append(
                    PartialError(
                        target_id=device.external_id,
                        endpoint=url,
                        status_code=500,
                        message="Missing result entry in batch response",
                    )
                )
                continue
            item = results[idx]
            status_code = int(item.get("status", 500))
            body = item.get("body")
            if status_code >= 400 or not isinstance(body, dict):
                errors.append(
                    PartialError(
                        target_id=device.external_id,
                        endpoint=f"{device.source_code}/{device.external_id}",
                        status_code=status_code,
                        message=str((body or {}).get("message", f"Batch item status {status_code}"))
                        if isinstance(body, dict)
                        else f"Batch item status {status_code}",
                    )
                )
                continue
            mapper = self._get_mapper(device.source_code)
            snapshots.append(
                mapper.map_payload(device, body, fallback_ts=datetime.now(timezone.utc))
            )

        return BatchTelemetryResult(snapshots=snapshots, errors=errors)
