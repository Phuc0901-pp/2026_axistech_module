"""Prompt 5 Unit Tests (UT-028 to UT-035): Telemetry Strategy Mappers, Batch Isolation, Chunker."""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
import respx

from axisstream_bridge.core.exceptions import ValidationError
from axisstream_bridge.domain.models import Device
from axisstream_bridge.infrastructure.axisstream.telemetry_client import (
    AxisStreamTelemetryClient,
    SoilProbeTelemetryMapper,
    WaterFlowTelemetryMapper,
    WaterLevelTelemetryMapper,
    WeatherTelemetryMapper,
    chunk_date_range,
)
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from tests.fixtures.axisstream_fixtures import (
    SOILPROBE_TELEMETRY_FIXTURE,
    WATERFLOW_TELEMETRY_FIXTURE,
    WATERLEVEL_EMPTY_FIXTURE,
    WEATHER_TELEMETRY_FIXTURE,
)


def _dev(ext_id: str, source: str) -> Device:
    return Device(id=f"id-{ext_id}", name=ext_id, external_id=ext_id, source_code=source)


def test_ut_028_waterflow_mapper_parses_string_metrics() -> None:
    snap = WaterFlowTelemetryMapper().map_payload(_dev("79DA26E0", "waterflow"), WATERFLOW_TELEMETRY_FIXTURE)
    assert snap.status == "LIVE"
    metrics = {r.metric: r for r in snap.readings}
    assert metrics["waterVolume"].value == 0.0
    assert metrics["waterVolume"].unit == "L"
    assert metrics["cumulativeWater"].value == 81.0
    assert snap.metadata.signal_strength_dbm == -33.0


def test_ut_029_soilprobe_mapper_reconciles_moist_to_moisture_across_depths() -> None:
    snap = SoilProbeTelemetryMapper().map_payload(_dev("79D75620", "soilprobe"), SOILPROBE_TELEMETRY_FIXTURE)
    depth3 = {r.metric: r for r in snap.readings if r.depth_level == 3}
    assert "moisture" in depth3
    assert depth3["moisture"].value == pytest.approx(10.96)
    assert depth3["moisture"].unit == "%"
    assert depth3["temperature"].value == pytest.approx(30.34)
    assert depth3["vic"].value == pytest.approx(957.0)


def test_ut_030_waterlevel_empty_and_epoch_sentinel_returns_no_data() -> None:
    snap = WaterLevelTelemetryMapper().map_payload(_dev("20001DC4", "waterlevel"), WATERLEVEL_EMPTY_FIXTURE)
    assert snap.status == "NO_DATA"
    assert snap.latest_timestamp_utc is None
    assert snap.readings == []
    assert snap.metadata.battery_level is None

    inactive_dev = Device(
        id="id-off", name="Inactive Probe", external_id="20001OFF", source_code="waterlevel", active=False
    )
    snap_off = WaterLevelTelemetryMapper().map_payload(inactive_dev, WATERLEVEL_EMPTY_FIXTURE)
    assert snap_off.status == "OFFLINE"


@respx.mock
async def test_ut_031_weather_mapper_12_metrics_and_optional_derived_fallback() -> None:
    snap = WeatherTelemetryMapper().map_payload(_dev("79DAAFB4", "weather"), WEATHER_TELEMETRY_FIXTURE)
    assert len(snap.readings) == 12
    metrics = {r.metric: r for r in snap.readings}
    assert metrics["temperature"].value == pytest.approx(30.4)
    assert metrics["uv_index"].unit == "index"

    respx.get("https://data.api.axisstream.co/device/tbncorp/weather_eto/79DAAFB4/device").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://data.api.axisstream.co/device/tbncorp/weather_indices/79DAAFB4/device").mock(
        return_value=httpx.Response(404)
    )
    http = ResilientHttpClient()
    client = AxisStreamTelemetryClient(http)
    try:
        assert await client.fetch_weather_derived_optional("tbncorp", "79DAAFB4", "weather_eto") is None
        assert await client.fetch_weather_derived_optional("tbncorp", "79DAAFB4", "weather_indices") is None
    finally:
        await http.aclose()


@respx.mock
async def test_ut_032_batch_telemetry_isolates_partial_failures() -> None:
    devices = [
        _dev("79DA26E0", "waterflow"),
        _dev("79D75620", "soilprobe"),
        _dev("20001DC4", "waterlevel"),
        _dev("79DAAFB4", "weather"),
    ]
    respx.post("https://data.api.axisstream.co/device/tbncorp/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"status": 200, "body": WATERFLOW_TELEMETRY_FIXTURE},
                    {"status": 200, "body": SOILPROBE_TELEMETRY_FIXTURE},
                    {"status": 500, "body": {"message": "Sensor timeout"}},
                    {"status": 404, "body": {"message": "Not found"}},
                ]
            },
        )
    )
    http = ResilientHttpClient()
    client = AxisStreamTelemetryClient(http)
    try:
        res = await client.fetch_batch_telemetry(
            "tbncorp", devices, date(2026, 11, 20), date(2026, 11, 26)
        )
        assert len(res.snapshots) == 2
        assert len(res.errors) == 2
        assert res.errors[0].target_id == "20001DC4"
        assert res.errors[0].status_code == 500
        assert res.errors[1].target_id == "79DAAFB4"
        assert res.errors[1].status_code == 404
    finally:
        await http.aclose()


def test_ut_033_date_range_chunking_boundaries() -> None:
    assert chunk_date_range(date(2026, 1, 1), date(2026, 1, 1), max_days=30) == [
        (date(2026, 1, 1), date(2026, 1, 1))
    ]
    chunks = chunk_date_range(date(2026, 1, 1), date(2026, 3, 31), max_days=30)
    assert len(chunks) == 3
    assert chunks[0][0] == date(2026, 1, 1)
    assert chunks[-1][1] == date(2026, 3, 31)
    with pytest.raises(ValidationError):
        chunk_date_range(date(2026, 2, 10), date(2026, 2, 1))


@respx.mock
async def test_ut_034_timezone_param_and_utc_output() -> None:
    route = respx.get("https://data.api.axisstream.co/device/tbncorp/waterflow/79DA26E0/device").mock(
        return_value=httpx.Response(200, json=WATERFLOW_TELEMETRY_FIXTURE)
    )
    http = ResilientHttpClient()
    client = AxisStreamTelemetryClient(http)
    try:
        snap = await client.fetch_device_telemetry(
            "tbncorp",
            _dev("79DA26E0", "waterflow"),
            date(2026, 11, 26),
            date(2026, 11, 26),
            "Asia/Ho_Chi_Minh",
        )
        assert route.calls[0].request.url.params["localTimeZone"] == "Asia/Ho_Chi_Minh"
        assert snap.readings[0].timestamp_utc.tzinfo == timezone.utc
    finally:
        await http.aclose()


def test_ut_035_unknown_sensor_code_uses_generic_fallback() -> None:
    http = ResilientHttpClient()
    client = AxisStreamTelemetryClient(http)
    mapper = client._get_mapper("canopy_monitoring")
    snap = mapper.map_payload(
        _dev("CANOPY1", "canopy_monitoring"),
        {
            "recentData": {"time": "2026-11-26T07:00:00.000Z", "canopy_temp": "28.4"},
            "uom": {"recentData.canopy_temp": "°C"},
        },
    )
    assert snap.status == "LIVE"
    assert snap.readings[0].metric == "canopy_temp"
    assert snap.readings[0].value == pytest.approx(28.4)
