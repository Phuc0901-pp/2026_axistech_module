"""Prompt 9 Unit Tests (UT-055 to UT-062): Live Auth, Exact AxisStream Contracts, MET Norway & Jane's Forecast."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
import httpx
import pytest
import respx

from axisstream_bridge.application.live_provider import LiveAxisStreamProvider
from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.domain.models import Device
from axisstream_bridge.infrastructure.auth.cookie_auth import (
    CookieSessionAuthenticator,
    create_axisstream_login_callback,
)
from axisstream_bridge.infrastructure.axisstream.alert_client import AxisStreamAlertClient
from axisstream_bridge.infrastructure.axisstream.forecast_client import AxisStreamForecastClient
from axisstream_bridge.infrastructure.axisstream.telemetry_client import (
    AxisStreamTelemetryClient,
    WeatherTelemetryMapper,
)
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from axisstream_bridge.interfaces.api.app import create_app
from tests.fixtures.axisstream_fixtures import (
    ALERT_POLICIES_FIXTURE,
    ASSETS_FIXTURE,
    DEVICES_FIXTURE_PAGE_1,
    EXCHANGE_FIXTURE,
    FIELDS_FIXTURE,
    PROJECT_LIST_FIXTURE,
)


@respx.mock
async def test_ut_055_live_login_callback_sends_exact_payload_and_extracts_cookies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    route = respx.post("https://v2.api.axisstream.co/api/account/login").mock(
        return_value=httpx.Response(
            200,
            json={"account": {"id": "acc-1"}},
            headers={"Set-Cookie": "ax_sid=synthetic-cookie-val; Path=/; HttpOnly"},
        )
    )
    login_cb = create_axisstream_login_callback(
        "https://v2.api.axisstream.co", "user@example.com", "synthetic-secret-pw"
    )
    auth = CookieSessionAuthenticator(login_cb)
    cookies = await auth.get_auth_cookies()

    assert cookies["ax_sid"] == "synthetic-cookie-val"
    sent = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert sent == {"email": "user@example.com", "password": "synthetic-secret-pw", "rememberMe": False}
    assert "synthetic-secret-pw" not in caplog.text
    assert "synthetic-cookie-val" not in caplog.text


@respx.mock
async def test_ut_056_batch_telemetry_uses_exact_items_envelope() -> None:
    from datetime import date

    route = respx.post("https://data.api.axisstream.co/device/tbncorp/batch").mock(
        return_value=httpx.Response(200, json={"results": [{"status": 200, "body": {"recentData": {}, "metadata": {}, "uom": {}, "timeSegments": {"latestDate": "1970-01-01T00:00:00Z"}}}]})
    )
    http = ResilientHttpClient()
    client = AxisStreamTelemetryClient(http)
    dev = Device(id="d1", name="Weather", external_id="79DAAFB4", source_code="weather")
    try:
        await client.fetch_batch_telemetry("tbncorp", [dev], date(2026, 11, 20), date(2026, 11, 26), "Asia/Phnom_Penh")
        body = json.loads(route.calls[0].request.content.decode("utf-8"))
        assert "items" in body and len(body["items"]) == 1
        assert body["items"][0]["deviceId"] == "79DAAFB4"
        assert body["items"][0]["uom"] == "metric"
    finally:
        await http.aclose()


def test_ut_057_weather_mapper_parses_live_camelcase_and_summary_rainfall() -> None:
    dev = Device(id="d1", name="TanBao Weather Station (A23)", external_id="79DAAFB4", source_code="weather")
    live_payload = {
        "recentData": {
            "time": "2026-11-26T07:54:00.000Z",
            "temperature": "36.40",
            "humidity": "53.16",
            "atmosPressure": "996.20",
            "mslPressure": "1007.40",
            "deltaT": "7.97",
            "dewPoint": "25.32",
            "windSpeed": "0.00",
            "windDirection": "S",
            "windGust": "0.00",
            "solarRadiation": "0",
            "uvIndex": "0",
        },
        "summaryData": {"rainfall": {"rainfallLast24hrs": "0"}},
        "metadata": {"time": "2026-11-26T07:54:00.000Z", "batteryLevel": "95", "signalStrength": "-66", "readingInterval": "17 mins"},
        "uom": {"recentData.temperature": "°C", "recentData.atmosPressure": "hPa", "summaryData.rainfall.rainfallLast24hrs": "mm"},
        "timeSegments": {"latestDate": "2026-11-26T07:54:00.000Z"},
    }
    snap = WeatherTelemetryMapper().map_payload(dev, live_payload)
    metrics = {r.metric: r for r in snap.readings}
    assert metrics["temperature"].value == pytest.approx(36.40)
    assert metrics["atmos_pressure"].value == pytest.approx(996.20)
    assert metrics["atmos_pressure"].unit == "hPa"
    assert metrics["wind_direction"].value == pytest.approx(180.0)
    assert metrics["rainfall_last_24hrs"].value == pytest.approx(0.0)


@respx.mock
async def test_ut_058_alert_history_parses_live_array_format() -> None:
    live_alerts = [
        {
            "id": "alrt-1",
            "status": "DELIVERED",
            "priority": "HIGH",
            "title": "Do am",
            "body": "Relative Humidity drops to or below 60 %",
            "originalEventTimestamp": "2026-11-26T07:54:00.000Z",
            "device": {"id": "d1", "name": "TanBao Weather Station (A23)"},
            "alertPolicy": {"id": "p1", "name": "Do am"},
            "notificationLogCount": {"logCount": 9},
            "pageInfo": {"total": 429, "totalPages": 3},
        }
    ]
    respx.get("https://v2.api.axisstream.co/api/alert/project/proj-1").mock(
        return_value=httpx.Response(200, json=live_alerts)
    )
    http = ResilientHttpClient()
    client = AxisStreamAlertClient(http)
    try:
        items = await client.list_alert_history("proj-1")
        assert len(items) == 1
        assert items[0].policy_name == "Do am"
        assert items[0].device_name == "TanBao Weather Station (A23)"
        assert items[0].notification_count == 9
    finally:
        await http.aclose()


def test_ut_059_metnorway_forecast_mapper() -> None:
    raw = {
        "location": {"latitude": 11.69, "longitude": 106.85, "timeZone": "Asia/Phnom_Penh", "utcOffsetMinutes": 420, "name": "Long Tân"},
        "model": {"updatedAt": "2026-11-26T07:00:00Z", "expiresAt": "2026-11-26T10:00:00Z"},
        "currentStepIndex": 0,
        "days": [
            {"date": f"2026-11-{26+i}", "complete": True, "hoursCovered": 24, "temperatureMin": 23.0, "temperatureMax": 32.0, "precipitation": 5.9, "symbol": "rainshowers_day"}
            for i in range(7)
        ],
        "steps": [
            {
                "time": "2026-11-26T08:00:00Z",
                "timeLocal": "2026-11-26T15:00",
                "intervalHours": 1,
                "isNight": False,
                "temperature": 32.0,
                "feelsLike": 37.0,
                "humidity": 59.0,
                "pressure": 1010.0,
                "windSpeed": 5.0,
                "windGust": 9.0,
                "windDirection": 327.0,
                "uvIndex": 2.6,
                "cloudCover": 16.0,
                "fog": 0.0,
                "next1h": {"symbol": "fair_day", "precipitation": 0.0, "probabilityOfPrecipitation": 10.0},
                "next6h": {"precipitation": 0.3},
            }
        ],
    }
    report = AxisStreamForecastClient.map_metnorway_payload(raw)
    assert report.status == "CONNECTED"
    assert report.location is not None and report.location.name == "Long Tân"
    assert len(report.days) == 7
    assert report.steps[0].feels_like == 37.0
    assert report.steps[0].precipitation_6h == 0.3


@respx.mock
async def test_ut_060_janes_weather_mapper_and_404_disconnected() -> None:
    raw_janes = {
        "location": {"name": "Long Tan", "latitude": 11.69, "longitude": 106.85},
        "days": [{"date": "2026-11-26", "minTemp": 24.0, "maxTemp": 33.0, "rainTotal": 1.2, "et0": 4.5, "symbol": "partly_cloudy"}],
        "hours": [{"time": "2026-11-26T08:00:00Z", "temp": 31.0, "deltaT": 6.2, "humidity": 60.0, "windSpeed": 8.0, "rain": 0.0}],
        "spray": {
            "hours": [{"time": "2026-11-26T08:00:00Z", "status": "IDEAL", "deltaT": 6.2, "windSpeed": 8.0, "reasons": ["Good DeltaT"]}],
            "windows": [{"start": "2026-11-26T08:00:00Z", "end": "2026-11-26T11:00:00Z", "durationHours": 3.0, "quality": "IDEAL"}],
        },
    }
    mapped = AxisStreamForecastClient.map_janes_payload(raw_janes)
    assert mapped.status == "CONNECTED"
    assert mapped.spray_hours[0].status == "IDEAL"
    assert mapped.spray_windows[0].duration_hours == 3.0

    respx.get("https://provider.api.axisstream.co/janes_weather/forecast/project/p1/provider/prov1").mock(
        return_value=httpx.Response(404)
    )
    http = ResilientHttpClient()
    client = AxisStreamForecastClient(http)
    try:
        res = await client.fetch_janes_forecast("p1", "prov1")
        assert res.status == "DISCONNECTED"
    finally:
        await http.aclose()


def test_ut_061_create_app_live_mode_and_forecast_endpoint() -> None:
    live_cfg = BridgeSettings(
        mode="live",
        auth_mode="cookie",
        axisstream_username="user@example.com",
        axisstream_password="synthetic-password",
        inbound_api_key="live-key-123",
    )
    app = create_app(live_cfg, enable_background_sync=False)
    prov = app.state.orchestrator._provider
    assert isinstance(prov, LiveAxisStreamProvider)

    demo_app = create_app(BridgeSettings(mode="demo", inbound_api_key="demo-key"), enable_background_sync=False)
    with TestClient(demo_app) as client:
        r = client.get(
            "/api/v1/projects/1b73e2fe-1e6c-46c6-8534-82c0e03be283/forecast",
            headers={"X-API-Key": "demo-key"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["met_norway"]["status"] == "CONNECTED"
        assert len(body["met_norway"]["days"]) == 7
        assert body["janes_weather"]["status"] == "DISCONNECTED"


@respx.mock
async def test_ut_062_live_provider_end_to_end_sync() -> None:
    pid = "1b73e2fe-1e6c-46c6-8534-82c0e03be283"
    pid2 = "1c623db4-80a3-4523-9aa4-979c8620a7a9"
    respx.get("https://v2.api.axisstream.co/api/project/list").mock(return_value=httpx.Response(200, json=PROJECT_LIST_FIXTURE))
    respx.get(f"https://v2.api.axisstream.co/api/device/project/{pid}").mock(return_value=httpx.Response(200, json=DEVICES_FIXTURE_PAGE_1))
    respx.get(f"https://v2.api.axisstream.co/api/device/project/{pid2}").mock(return_value=httpx.Response(200, json={"data": [], "meta": {"hasNextPage": False}}))
    respx.get(f"https://v2.api.axisstream.co/api/field/project/{pid}").mock(return_value=httpx.Response(200, json=FIELDS_FIXTURE))
    respx.get(f"https://v2.api.axisstream.co/api/field/project/{pid2}").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"https://v2.api.axisstream.co/api/asset/project/{pid}").mock(return_value=httpx.Response(200, json=ASSETS_FIXTURE))
    respx.get(f"https://v2.api.axisstream.co/api/asset/project/{pid2}").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.get(f"https://v2.api.axisstream.co/api/alert/policies/project/{pid}").mock(return_value=httpx.Response(200, json=ALERT_POLICIES_FIXTURE))
    respx.get(f"https://v2.api.axisstream.co/api/alert/policies/project/{pid2}").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"https://v2.api.axisstream.co/api/alert/project/{pid}").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"https://v2.api.axisstream.co/api/alert/project/{pid2}").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"https://v2.api.axisstream.co/api/provider/project/{pid}").mock(return_value=httpx.Response(404))
    respx.get(f"https://v2.api.axisstream.co/api/provider/project/{pid2}").mock(return_value=httpx.Response(404))
    respx.get(f"https://v2.api.axisstream.co/api/exchange/project/{pid}").mock(return_value=httpx.Response(200, json=EXCHANGE_FIXTURE))
    respx.get(f"https://v2.api.axisstream.co/api/exchange/project/{pid2}").mock(return_value=httpx.Response(200, json=[]))
    respx.post("https://data.api.axisstream.co/device/tbncorp/batch").mock(
        return_value=httpx.Response(200, json={"results": [{"status": 200, "body": {"recentData": {"time": "2026-11-26T07:54:00Z", "temperature": "36.4"}, "uom": {"recentData.temperature": "°C"}, "timeSegments": {"latestDate": "2026-11-26T07:54:00Z"}}}]})
    )
    respx.get("https://data.api.axisstream.co/exchange/tbncorp/weather").mock(return_value=httpx.Response(404))
    respx.get("https://data.api.axisstream.co/device/tbncorp/weather/79DAAFB4/device").mock(
        return_value=httpx.Response(200, json={"recentData": {"time": "2026-11-26T07:54:00Z", "temperature": "36.4"}, "timeSegments": {"latestDate": "2026-11-26T07:54:00Z"}})
    )
    respx.get(f"https://provider.api.axisstream.co/metnorway/forecast/project/{pid}/provider/4c052fb9-d254-4f3e-9b2d-1ab64b86e91c").mock(
        return_value=httpx.Response(200, json={"location": {"name": "Long Tan"}, "days": [{"date": "2026-11-26", "temperatureMin": 24, "temperatureMax": 32}], "steps": []})
    )
    respx.get(f"https://provider.api.axisstream.co/metnorway/forecast/project/{pid2}/provider/4c052fb9-d254-4f3e-9b2d-1ab64b86e91c").mock(
        return_value=httpx.Response(404)
    )

    http = ResilientHttpClient()
    cfg = BridgeSettings(mode="live", axisstream_username="user@example.com", axisstream_password="synthetic-password")
    provider = LiveAxisStreamProvider(cfg, http_client=http)
    try:
        bundle = await provider.fetch_project_forecast(pid)
        assert bundle.met_norway.status == "CONNECTED"
        assert bundle.janes_weather.status == "DISCONNECTED"
        rows = await provider.fetch_weather_exchange("tbncorp", pid)
        assert len(rows) == 1 and rows[0].temperature_avg == pytest.approx(36.4)
    finally:
        await http.aclose()
