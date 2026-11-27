"""Pure ISO 8601, ISO 80000, GeoJSON, and SSRF path-safety normalizers."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
import math
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from axisstream_bridge.core.exceptions import SecurityViolationError, ValidationError

EPOCH_SENTINEL_CUTOFF = datetime(1970, 1, 2, 0, 0, 0, tzinfo=timezone.utc)

UNIT_REGISTRY: dict[str, str] = {
    "°C": "°C",
    "C": "°C",
    "degC": "°C",
    "%": "%",
    "pct": "%",
    "mm": "mm",
    "hPa": "hPa",
    "km/h": "km/h",
    "kph": "km/h",
    "W/m²": "W/m²",
    "W/m2": "W/m²",
    "L": "L",
    "l": "L",
    "m": "m",
    "V": "V",
    "v": "V",
    "dBm": "dBm",
    "VIC": "VIC",
    "deg": "deg",
    "°": "deg",
    "index": "index",
    "": "",
}

_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_US_SHORT_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_LOCALE_DATETIME_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4}),\s*(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)$",
    re.IGNORECASE,
)


def _resolve_tz(tz_name: str) -> tzinfo:
    if tz_name.upper() in ("UTC", "Z"):
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def parse_iso_timestamp(
    value: Any,
    *,
    default_tz: str = "UTC",
) -> datetime | None:
    """Parse AxisStream mixed date/time strings into UTC-aware datetime.

    Supports:
    - ISO 8601 (`2026-01-28T10:28:24.000Z`, `2024-08-07T17:14:41.933+00:00`)
    - US short date (`12/2/2025`)
    - Locale timestamp (`2/15/2053, 2:53:43 PM`, `8/7/2024, 5:14:41 PM`)

    Returns None for null/empty values or Epoch sentinels (<= 1970-01-02 UTC).
    """
    if value is None:
        return None
    tz = _resolve_tz(default_tz)
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=tz)
        dt_utc = dt.astimezone(timezone.utc)
        return None if dt_utc <= EPOCH_SENTINEL_CUTOFF else dt_utc

    text = str(value).strip()
    if not text:
        return None

    dt_parsed: datetime | None = None

    # 1. Locale datetime: M/D/YYYY, H:MM:SS AM/PM
    m_loc = _LOCALE_DATETIME_RE.match(text)
    if m_loc:
        month, day, year, hour, minute, second, ampm = m_loc.groups()
        h = int(hour)
        if ampm.upper() == "PM" and h != 12:
            h += 12
        elif ampm.upper() == "AM" and h == 12:
            h = 0
        dt_parsed = datetime(
            int(year), int(month), int(day), h, int(minute), int(second),
            tzinfo=tz,
        )
    else:
        # 2. US short date: M/D/YYYY
        m_short = _US_SHORT_DATE_RE.match(text)
        if m_short:
            month, day, year = m_short.groups()
            dt_parsed = datetime(
                int(year), int(month), int(day), 0, 0, 0,
                tzinfo=tz,
            )
        else:
            # 3. ISO 8601
            iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                dt_parsed = datetime.fromisoformat(iso_candidate)
            except ValueError as exc:
                raise ValidationError(f"Unparseable timestamp: {text!r}") from exc
            if dt_parsed.tzinfo is None:
                dt_parsed = dt_parsed.replace(tzinfo=tz)

    dt_utc = dt_parsed.astimezone(timezone.utc)
    if dt_utc <= EPOCH_SENTINEL_CUTOFF:
        return None
    return dt_utc


def parse_numeric(value: Any, *, strict: bool = False) -> float | None:
    """Safely parse AxisStream string-encoded numbers into finite floats."""
    if value is None or isinstance(value, bool):
        if strict and value is not None:
            raise ValidationError(f"Boolean is not numeric: {value!r}")
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    else:
        text = str(value).strip()
        if not text or text.upper() in ("N/A", "NA", "NULL", "NONE", "-"):
            return None
        try:
            num = float(text)
        except ValueError as exc:
            if strict:
                raise ValidationError(f"Invalid numeric value: {text!r}") from exc
            return None

    if not math.isfinite(num):
        if strict:
            raise ValidationError(f"Non-finite numeric value: {value!r}")
        return None
    return num


def normalize_unit(raw_unit: str | None) -> str:
    """Normalize measurement units against ISO 80000 / AxisStream unit registry."""
    if raw_unit is None:
        return ""
    cleaned = raw_unit.strip()
    return UNIT_REGISTRY.get(cleaned, cleaned)


def validate_coordinates(lon: float, lat: float) -> None:
    """Validate WGS84 longitude and latitude bounds."""
    if not (-180.0 <= lon <= 180.0):
        raise ValidationError(f"Longitude out of range [-180, 180]: {lon}")
    if not (-90.0 <= lat <= 90.0):
        raise ValidationError(f"Latitude out of range [-90, 90]: {lat}")


def _validate_polygon_ring(ring: list[Any]) -> None:
    if len(ring) < 4:
        raise ValidationError("GeoJSON Polygon ring must have at least 4 positions")
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            raise ValidationError(f"Invalid GeoJSON coordinate point: {pt!r}")
        validate_coordinates(float(pt[0]), float(pt[1]))
    if list(ring[0][:2]) != list(ring[-1][:2]):
        raise ValidationError("GeoJSON Polygon ring must be closed (first == last coordinate)")


def validate_geojson_geometry(geojson: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate Point, Polygon, Feature, or FeatureCollection GeoJSON payloads."""
    if geojson is None:
        return None
    gtype = geojson.get("type")
    if gtype == "FeatureCollection":
        features = geojson.get("features")
        if not isinstance(features, list):
            raise ValidationError("FeatureCollection 'features' must be a list")
        for feat in features:
            validate_geojson_geometry(feat)
        return geojson
    if gtype == "Feature":
        geom = geojson.get("geometry")
        if geom is not None:
            validate_geojson_geometry(geom)
        return geojson
    if gtype == "Point":
        coords = geojson.get("coordinates", [])
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            raise ValidationError("GeoJSON Point requires [lon, lat]")
        validate_coordinates(float(coords[0]), float(coords[1]))
        return geojson
    if gtype == "Polygon":
        rings = geojson.get("coordinates", [])
        if not isinstance(rings, list) or not rings:
            raise ValidationError("GeoJSON Polygon requires non-empty coordinate rings")
        for ring in rings:
            _validate_polygon_ring(ring)
        return geojson
    raise ValidationError(f"Unsupported GeoJSON type: {gtype!r}")


def validate_safe_path_segment(value: str, field_name: str = "segment") -> str:
    """Ensure dynamic URL path segments cannot perform path traversal or SSRF injection."""
    cleaned = value.strip()
    if not cleaned or ".." in cleaned or not _SAFE_SEGMENT_RE.match(cleaned):
        raise SecurityViolationError(
            f"Unsafe path segment for {field_name}: {value!r}"
        )
    return cleaned
