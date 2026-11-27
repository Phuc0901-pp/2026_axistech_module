"""Canonical immutable domain entities (ISO/IEC/IEEE 42010:2022).

STRICT LAYER BOUNDARY: This module may only import stdlib, pydantic, core, and domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CanonicalModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Organisation(CanonicalModel):
    id: str
    name: str
    schema_name: str
    pbi_workspace: str | None = None


class ProjectAccess(CanonicalModel):
    hq: list[str] = Field(default_factory=list)
    my: list[str] = Field(default_factory=list)
    fm4d: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)
    field_app: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)


class Project(CanonicalModel):
    id: str
    name: str
    description: str = ""
    role: str = "VIEWER"
    organisation: Organisation
    access: ProjectAccess = Field(default_factory=ProjectAccess)


class Coordinates(CanonicalModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class Device(CanonicalModel):
    id: str
    name: str
    description: str = ""
    external_id: str
    source_code: str
    sensor_set_code: str = ""
    comm_type: str = ""
    active: bool = True
    preferred_uom: str = "metric"
    coordinates: Coordinates | None = None
    updated_at: datetime | None = None


class GeoPolygonSite(CanonicalModel):
    id: str
    name: str
    category: str = "Other"
    geojson: dict[str, Any] | None = None
    area: float | None = None


class FieldLocation(CanonicalModel):
    id: str
    project_id: str
    name: str
    category: str = "Other"
    address: str = ""
    is_default: bool = False
    sites: list[GeoPolygonSite] = Field(default_factory=list)


class Asset(CanonicalModel):
    id: str
    project_id: str
    name: str
    asset_type: str
    description: str = ""
    make: str = ""
    model: str = ""
    number_plate: str | None = None
    capacity_litres: float | None = None
    position: Coordinates | None = None


class TelemetryReading(CanonicalModel):
    device_id: str
    external_id: str
    source_code: str
    metric: str
    value: float | None
    unit: str = ""
    depth_level: int | None = None
    timestamp_utc: datetime

    @field_validator("timestamp_utc")
    @classmethod
    def _require_tz_aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("TelemetryReading.timestamp_utc must be timezone-aware")
        return v


class DeviceMetadata(CanonicalModel):
    last_reported_utc: datetime | None = None
    battery_level: float | None = None
    signal_strength_dbm: float | None = None
    reading_interval: str | None = None


class DeviceTelemetrySnapshot(CanonicalModel):
    device_id: str
    external_id: str
    source_code: str
    status: Literal["LIVE", "LATE", "OFFLINE", "NO_DATA"]
    latest_timestamp_utc: datetime | None = None
    earliest_timestamp_utc: datetime | None = None
    readings: list[TelemetryReading] = Field(default_factory=list)
    metadata: DeviceMetadata = Field(default_factory=DeviceMetadata)
    uom: dict[str, str] = Field(default_factory=dict)


class PartialError(CanonicalModel):
    target_id: str
    endpoint: str
    status_code: int
    message: str


class BatchTelemetryResult(CanonicalModel):
    snapshots: list[DeviceTelemetrySnapshot] = Field(default_factory=list)
    errors: list[PartialError] = Field(default_factory=list)


class AlertCondition(CanonicalModel):
    name: str
    condition_type: str = "value"
    column: str
    operator: str
    threshold: str


class AlertPolicy(CanonicalModel):
    id: str
    project_id: str
    name: str
    entity_id: str
    entity_type: str = "device"
    device_name: str = ""
    status: str
    priority: str
    frequency_window_minutes: int = 60
    notification_types: list[str] = Field(default_factory=list)
    conditions: list[AlertCondition] = Field(default_factory=list)
    message_template: str = ""


class AlertHistoryItem(CanonicalModel):
    id: str
    project_id: str
    policy_name: str
    device_name: str = ""
    rule_description: str = ""
    delivery_status: str = "Delivered"
    notification_count: int = 0
    triggered_at_utc: datetime | None = None


class ProviderConnection(CanonicalModel):
    id: str
    name: str
    code: str = ""
    status: str = "CONNECTED"


class ExchangeDataset(CanonicalModel):
    table_id: str
    table_name: str
    schema_name: str
    columns: list[str] = Field(default_factory=list)


class ExchangeTokenInfo(CanonicalModel):
    token_id: str
    name: str
    status: str
    valid_until_utc: datetime | None = None
    default_rows_per_request: int = 15000
    unrestricted_devices: bool = True
    datasets: list[ExchangeDataset] = Field(default_factory=list)


class WeatherExchangeRow(CanonicalModel):
    """All 17 observed columns from tbncorp.weather API Exchange dataset."""

    code: str
    time: datetime
    temperature_avg: float | None = None
    humidity_avg: float | None = None
    deltat_avg: float | None = None
    dewpoint_avg: float | None = None
    atmos_pressure_avg: float | None = None
    msl_pressure: float | None = None
    rainfall: float | None = None
    rainfall_total: float | None = None
    wind_speed_avg: float | None = None
    wind_speed_min: float | None = None
    wind_speed_max: float | None = None
    wind_dir_deg_avg: float | None = None
    wind_dir_var_avg: float | None = None
    solar_rad_avg: float | None = None
    uv_index_avg: float | None = None


class SyncDeltaEvent(CanonicalModel):
    event_id: str
    event_type: Literal["telemetry_update", "alert_update", "sync_complete", "heartbeat"]
    project_id: str
    timestamp_utc: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ForecastLocation(CanonicalModel):
    name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    elevation: float | None = None
    time_zone: str = ""
    utc_offset_minutes: int | None = None


class ForecastDay(CanonicalModel):
    date: str
    complete: bool = True
    hours_covered: int | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    precipitation: float | None = None
    symbol: str = ""
    rain_prob: float | None = None
    wind_max: float | None = None
    uv_max: float | None = None
    solar_total: float | None = None
    et0: float | None = None
    summary: str = ""


class ForecastStep(CanonicalModel):
    time_utc: datetime
    time_local: str = ""
    interval_hours: int = 1
    is_night: bool = False
    temperature: float | None = None
    feels_like: float | None = None
    dew_point: float | None = None
    delta_t: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    wind_speed: float | None = None
    wind_gust: float | None = None
    wind_direction: float | None = None
    uv_index: float | None = None
    cloud_cover: float | None = None
    cloud_cover_low: float | None = None
    cloud_cover_medium: float | None = None
    cloud_cover_high: float | None = None
    fog: float | None = None
    precipitation_1h: float | None = None
    precipitation_6h: float | None = None
    rain_prob: float | None = None
    symbol: str = ""


class SprayHour(CanonicalModel):
    time_utc: datetime
    status: str = "CAUTION"
    delta_t: float | None = None
    wind_speed: float | None = None
    rain_prob: float | None = None
    inversion_risk: str = ""
    reasons: list[str] = Field(default_factory=list)


class SprayWindow(CanonicalModel):
    start_utc: datetime
    end_utc: datetime
    duration_hours: float | None = None
    quality: str = ""


class WeatherForecastReport(CanonicalModel):
    provider: str
    status: Literal["CONNECTED", "DISCONNECTED", "ERROR"] = "DISCONNECTED"
    location: ForecastLocation | None = None
    updated_at_utc: datetime | None = None
    expires_at_utc: datetime | None = None
    current_step_index: int = 0
    days: list[ForecastDay] = Field(default_factory=list)
    steps: list[ForecastStep] = Field(default_factory=list)
    spray_hours: list[SprayHour] = Field(default_factory=list)
    spray_windows: list[SprayWindow] = Field(default_factory=list)
    error_message: str = ""


class ProjectForecastBundle(CanonicalModel):
    project_id: str
    met_norway: WeatherForecastReport
    janes_weather: WeatherForecastReport
