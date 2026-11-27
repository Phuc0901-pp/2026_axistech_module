"""Prompt 2 Unit Tests (UT-006 to UT-012): Domain ISO Normalizers & Architecture Boundary."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from axisstream_bridge.core.exceptions import ValidationError
from axisstream_bridge.domain.models import TelemetryReading
from axisstream_bridge.domain.normalizers import (
    normalize_unit,
    parse_iso_timestamp,
    parse_numeric,
    validate_geojson_geometry,
)
from tests.fixtures.axisstream_fixtures import FIELDS_FIXTURE


def test_ut_006_multi_format_date_parsing_to_utc() -> None:
    dt1 = parse_iso_timestamp("2026-01-28T10:28:24.000Z")
    assert dt1 == datetime(2026, 1, 28, 10, 28, 24, tzinfo=timezone.utc)

    dt2 = parse_iso_timestamp("12/2/2025")
    assert dt2 == datetime(2025, 12, 2, 0, 0, 0, tzinfo=timezone.utc)

    dt3 = parse_iso_timestamp("2/15/2053, 2:53:43 PM")
    assert dt3 == datetime(2053, 2, 15, 14, 53, 43, tzinfo=timezone.utc)


def test_ut_007_epoch_sentinel_returns_none() -> None:
    assert parse_iso_timestamp("1970-01-01T00:00:00.000Z") is None
    assert parse_iso_timestamp(None) is None
    assert parse_iso_timestamp("   ") is None


def test_ut_008_numeric_strings_and_boundary_values() -> None:
    assert parse_numeric("0.00") == 0.0
    assert parse_numeric("-92") == -92.0
    assert parse_numeric("29.53") == 29.53
    assert parse_numeric("") is None
    assert parse_numeric("N/A") is None
    assert parse_numeric("NaN") is None
    assert parse_numeric("Infinity") is None
    with pytest.raises(ValidationError):
        parse_numeric("NaN", strict=True)


def test_ut_009_unit_normalization() -> None:
    assert normalize_unit("degC") == "°C"
    assert normalize_unit("kph") == "km/h"
    assert normalize_unit("W/m2") == "W/m²"
    assert normalize_unit("VIC") == "VIC"
    assert normalize_unit("custom_unit") == "custom_unit"


def test_ut_010_geojson_validation_boundaries() -> None:
    valid_geo = FIELDS_FIXTURE["data"][0]["sites"][0]["geojson"]
    assert validate_geojson_geometry(valid_geo) == valid_geo

    with pytest.raises(ValidationError, match="Latitude"):
        validate_geojson_geometry({"type": "Point", "coordinates": [106.0, 90.0001]})

    with pytest.raises(ValidationError, match="Longitude"):
        validate_geojson_geometry({"type": "Point", "coordinates": [-180.0001, 11.0]})

    with pytest.raises(ValidationError, match="closed"):
        validate_geojson_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[106.0, 11.0], [106.1, 11.0], [106.1, 11.1], [106.0, 11.1]]],
            }
        )


def test_ut_011_domain_invariants_require_tz_aware_and_frozen() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TelemetryReading(
            device_id="d1",
            external_id="e1",
            source_code="weather",
            metric="temperature",
            value=25.0,
            timestamp_utc=datetime(2026, 1, 1, 0, 0, 0),
        )
    reading = TelemetryReading(
        device_id="d1",
        external_id="e1",
        source_code="weather",
        metric="temperature",
        value=25.0,
        timestamp_utc=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(Exception):
        reading.value = 30.0  # type: ignore[misc]


def test_ut_012_domain_layer_has_no_infrastructure_imports() -> None:
    domain_dir = Path(__file__).resolve().parents[2] / "src" / "axisstream_bridge" / "domain"
    forbidden = {"httpx", "fastapi", "sqlite3", "uvicorn", "starlette"}
    for py_file in domain_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden, f"{py_file} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden, f"{py_file} imports {node.module}"
