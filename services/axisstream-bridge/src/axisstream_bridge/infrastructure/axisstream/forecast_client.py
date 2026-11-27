"""AxisStream Weather Forecast adapter for MET Norway & Jane's Weather."""

from __future__ import annotations

import logging
from typing import Any

from axisstream_bridge.core.exceptions import AxisStreamError, ValidationError
from axisstream_bridge.domain.models import (
    ForecastDay,
    ForecastLocation,
    ForecastStep,
    SprayHour,
    SprayWindow,
    WeatherForecastReport,
)
from axisstream_bridge.domain.normalizers import (
    parse_iso_timestamp,
    parse_numeric,
    validate_safe_path_segment,
)
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient

logger = logging.getLogger("axisstream_bridge.acl.forecast")


class AxisStreamForecastClient:
    """Fetches and normalizes MET Norway and Jane's Weather forecasts from provider.api.axisstream.co."""

    def __init__(
        self,
        http: ResilientHttpClient,
        provider_base_url: str = "https://provider.api.axisstream.co",
    ) -> None:
        self._http = http
        self._base_url = provider_base_url.rstrip("/")

    @staticmethod
    def map_metnorway_payload(raw: dict[str, Any]) -> WeatherForecastReport:
        loc_raw = raw.get("location") or {}
        location = ForecastLocation(
            name=str(loc_raw.get("name") or loc_raw.get("label") or ""),
            latitude=parse_numeric(loc_raw.get("latitude")),
            longitude=parse_numeric(loc_raw.get("longitude")),
            elevation=parse_numeric(loc_raw.get("elevation")),
            time_zone=str(loc_raw.get("timeZone") or ""),
            utc_offset_minutes=int(loc_raw["utcOffsetMinutes"])
            if loc_raw.get("utcOffsetMinutes") is not None
            else None,
        )
        model_raw = raw.get("model") or {}
        days: list[ForecastDay] = []
        for d in raw.get("days") or []:
            days.append(
                ForecastDay(
                    date=str(d.get("date") or ""),
                    complete=bool(d.get("complete", True)),
                    hours_covered=int(d["hoursCovered"]) if d.get("hoursCovered") is not None else None,
                    temperature_min=parse_numeric(d.get("temperatureMin")),
                    temperature_max=parse_numeric(d.get("temperatureMax")),
                    precipitation=parse_numeric(d.get("precipitation")),
                    symbol=str(d.get("symbol") or ""),
                )
            )

        steps: list[ForecastStep] = []
        for s in raw.get("steps") or []:
            t_utc = parse_iso_timestamp(s.get("time"))
            if t_utc is None:
                continue
            next1 = s.get("next1h") or {}
            next6 = s.get("next6h") or {}
            steps.append(
                ForecastStep(
                    time_utc=t_utc,
                    time_local=str(s.get("timeLocal") or ""),
                    interval_hours=int(s.get("intervalHours") or 1),
                    is_night=bool(s.get("isNight", False)),
                    temperature=parse_numeric(s.get("temperature")),
                    feels_like=parse_numeric(s.get("feelsLike")),
                    humidity=parse_numeric(s.get("humidity")),
                    pressure=parse_numeric(s.get("pressure")),
                    wind_speed=parse_numeric(s.get("windSpeed")),
                    wind_gust=parse_numeric(s.get("windGust")),
                    wind_direction=parse_numeric(s.get("windDirection")),
                    uv_index=parse_numeric(s.get("uvIndex")),
                    cloud_cover=parse_numeric(s.get("cloudCover")),
                    cloud_cover_low=parse_numeric(s.get("cloudCoverLow")),
                    cloud_cover_medium=parse_numeric(s.get("cloudCoverMedium")),
                    cloud_cover_high=parse_numeric(s.get("cloudCoverHigh")),
                    fog=parse_numeric(s.get("fog")),
                    precipitation_1h=parse_numeric(next1.get("precipitation")),
                    precipitation_6h=parse_numeric(next6.get("precipitation")),
                    rain_prob=parse_numeric(
                        next1.get("probabilityOfPrecipitation")
                        if next1.get("probabilityOfPrecipitation") is not None
                        else next6.get("probabilityOfPrecipitation")
                    ),
                    symbol=str(next1.get("symbol") or next6.get("symbol") or ""),
                )
            )

        return WeatherForecastReport(
            provider="MET Norway",
            status="CONNECTED",
            location=location,
            updated_at_utc=parse_iso_timestamp(model_raw.get("updatedAt") or model_raw.get("runAt")),
            expires_at_utc=parse_iso_timestamp(model_raw.get("expiresAt")),
            current_step_index=int(raw.get("currentStepIndex") or 0),
            days=days,
            steps=steps,
        )

    @staticmethod
    def map_janes_payload(raw: dict[str, Any]) -> WeatherForecastReport:
        loc_raw = raw.get("location") or {}
        location = ForecastLocation(
            name=str(loc_raw.get("name") or ""),
            latitude=parse_numeric(loc_raw.get("latitude")),
            longitude=parse_numeric(loc_raw.get("longitude")),
        )
        days: list[ForecastDay] = []
        for d in raw.get("days") or []:
            days.append(
                ForecastDay(
                    date=str(d.get("date") or ""),
                    temperature_min=parse_numeric(d.get("minTemp")),
                    temperature_max=parse_numeric(d.get("maxTemp")),
                    precipitation=parse_numeric(d.get("rainTotal")),
                    rain_prob=parse_numeric(d.get("rainProb")),
                    wind_max=parse_numeric(d.get("windMax")),
                    uv_max=parse_numeric(d.get("uvMax")),
                    solar_total=parse_numeric(d.get("solarTotal")),
                    et0=parse_numeric(d.get("et0")),
                    symbol=str(d.get("symbol") or ""),
                    summary=str(d.get("summary") or ""),
                )
            )

        steps: list[ForecastStep] = []
        for h in raw.get("hours") or []:
            t_utc = parse_iso_timestamp(h.get("time"))
            if t_utc is None:
                continue
            steps.append(
                ForecastStep(
                    time_utc=t_utc,
                    temperature=parse_numeric(h.get("temp")),
                    feels_like=parse_numeric(h.get("feelsLike")),
                    dew_point=parse_numeric(h.get("dewPoint")),
                    delta_t=parse_numeric(h.get("deltaT")),
                    humidity=parse_numeric(h.get("humidity")),
                    pressure=parse_numeric(h.get("pressure")),
                    wind_speed=parse_numeric(h.get("windSpeed")),
                    wind_gust=parse_numeric(h.get("windGust")),
                    wind_direction=parse_numeric(h.get("windDirDeg")),
                    uv_index=parse_numeric(h.get("uv")),
                    cloud_cover=parse_numeric(h.get("cloudPct")),
                    precipitation_1h=parse_numeric(h.get("rain")),
                    rain_prob=parse_numeric(h.get("rainProb")),
                    symbol=str(h.get("symbol") or ""),
                )
            )

        spray_raw = raw.get("spray") or {}
        spray_hours: list[SprayHour] = []
        for sh in spray_raw.get("hours") or []:
            t_utc = parse_iso_timestamp(sh.get("time"))
            if t_utc is None:
                continue
            spray_hours.append(
                SprayHour(
                    time_utc=t_utc,
                    status=str(sh.get("status") or "CAUTION"),
                    delta_t=parse_numeric(sh.get("deltaT")),
                    wind_speed=parse_numeric(sh.get("windSpeed")),
                    rain_prob=parse_numeric(sh.get("rainProb")),
                    inversion_risk=str(sh.get("inversionRisk") or ""),
                    reasons=[str(r) for r in (sh.get("reasons") or [])],
                )
            )

        spray_windows: list[SprayWindow] = []
        for sw in spray_raw.get("windows") or []:
            st = parse_iso_timestamp(sw.get("start"))
            en = parse_iso_timestamp(sw.get("end"))
            if st is None or en is None:
                continue
            spray_windows.append(
                SprayWindow(
                    start_utc=st,
                    end_utc=en,
                    duration_hours=parse_numeric(sw.get("durationHours")),
                    quality=str(sw.get("quality") or ""),
                )
            )

        return WeatherForecastReport(
            provider="Jane's Weather",
            status="CONNECTED",
            location=location,
            days=days,
            steps=steps,
            spray_hours=spray_hours,
            spray_windows=spray_windows,
        )

    async def fetch_metnorway_forecast(
        self, project_id: str, provider_id: str
    ) -> WeatherForecastReport:
        if not provider_id.strip():
            return WeatherForecastReport(provider="MET Norway", status="DISCONNECTED")
        pid = validate_safe_path_segment(project_id, "project_id")
        prov = validate_safe_path_segment(provider_id, "provider_id")
        try:
            raw = await self._http.request_json(
                "GET",
                f"{self._base_url}/metnorway/forecast/project/{pid}/provider/{prov}",
            )
            if not isinstance(raw, dict):
                return WeatherForecastReport(provider="MET Norway", status="DISCONNECTED")
            return self.map_metnorway_payload(raw)
        except ValidationError:
            return WeatherForecastReport(provider="MET Norway", status="DISCONNECTED")
        except AxisStreamError as exc:
            logger.warning("MET Norway forecast unavailable", extra={"error": exc.code})
            return WeatherForecastReport(
                provider="MET Norway",
                status="ERROR",
                error_message=str(exc),
            )

    async def fetch_janes_forecast(
        self, project_id: str, provider_id: str
    ) -> WeatherForecastReport:
        if not provider_id.strip():
            return WeatherForecastReport(provider="Jane's Weather", status="DISCONNECTED")
        pid = validate_safe_path_segment(project_id, "project_id")
        prov = validate_safe_path_segment(provider_id, "provider_id")
        try:
            raw = await self._http.request_json(
                "GET",
                f"{self._base_url}/janes_weather/forecast/project/{pid}/provider/{prov}",
            )
            if not isinstance(raw, dict):
                return WeatherForecastReport(provider="Jane's Weather", status="DISCONNECTED")
            return self.map_janes_payload(raw)
        except ValidationError:
            return WeatherForecastReport(provider="Jane's Weather", status="DISCONNECTED")
        except AxisStreamError as exc:
            logger.warning("Jane's Weather forecast unavailable", extra={"error": exc.code})
            return WeatherForecastReport(
                provider="Jane's Weather",
                status="ERROR",
                error_message=str(exc),
            )
