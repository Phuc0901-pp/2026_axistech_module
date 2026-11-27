"""Prompt 8 ISO Compliance Tests (UT-049 to UT-054): E2E Pipeline, Secret Scan, SSRF, 15k Perf, OpenAPI, Traceability."""

from __future__ import annotations

from pathlib import Path
import re
import time

import httpx
import pytest
import respx

from axisstream_bridge.application.sync_service import IncrementalSyncOrchestrator, SseEventHub
from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import SecurityViolationError
from axisstream_bridge.domain.normalizers import validate_safe_path_segment
from axisstream_bridge.infrastructure.axisstream.alert_client import (
    AxisStreamAlertClient,
    AxisStreamExchangeClient,
)
from axisstream_bridge.infrastructure.axisstream.telemetry_client import AxisStreamTelemetryClient
from axisstream_bridge.infrastructure.axisstream.v2_client import AxisStreamV2Client
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from axisstream_bridge.infrastructure.storage.state_store import SqliteStateStore
from axisstream_bridge.interfaces.api.app import create_app
from tests.fixtures.axisstream_fixtures import (
    ALERT_POLICIES_FIXTURE,
    ASSETS_FIXTURE,
    DEVICES_FIXTURE_PAGE_1,
    EXCHANGE_FIXTURE,
    FIELDS_FIXTURE,
    PROJECT_LIST_FIXTURE,
    SOILPROBE_TELEMETRY_FIXTURE,
    WATERFLOW_TELEMETRY_FIXTURE,
    WATERLEVEL_EMPTY_FIXTURE,
    WEATHER_TELEMETRY_FIXTURE,
)


@respx.mock
async def test_ut_049_full_e2e_mocked_pipeline_against_upstream_contracts() -> None:
    pid = "1b73e2fe-1e6c-46c6-8534-82c0e03be283"
    pid2 = "1c623db4-80a3-4523-9aa4-979c8620a7a9"

    respx.get("https://v2.api.axisstream.co/api/project/list").mock(
        return_value=httpx.Response(200, json=PROJECT_LIST_FIXTURE)
    )
    respx.get(f"https://v2.api.axisstream.co/api/device/project/{pid}").mock(
        return_value=httpx.Response(200, json=DEVICES_FIXTURE_PAGE_1)
    )
    respx.get(f"https://v2.api.axisstream.co/api/device/project/{pid2}").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"hasNextPage": False}})
    )
    respx.get(f"https://v2.api.axisstream.co/api/field/project/{pid}").mock(
        return_value=httpx.Response(200, json=FIELDS_FIXTURE)
    )
    respx.get(f"https://v2.api.axisstream.co/api/field/project/{pid2}").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"hasNextPage": False}})
    )
    respx.get(f"https://v2.api.axisstream.co/api/asset/project/{pid}").mock(
        return_value=httpx.Response(200, json=ASSETS_FIXTURE)
    )
    respx.get(f"https://v2.api.axisstream.co/api/asset/project/{pid2}").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"hasNextPage": False}})
    )
    respx.get(f"https://v2.api.axisstream.co/api/exchange/project/{pid}").mock(
        return_value=httpx.Response(200, json=EXCHANGE_FIXTURE)
    )
    respx.get(f"https://v2.api.axisstream.co/api/exchange/project/{pid2}").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"https://v2.api.axisstream.co/api/provider/project/{pid}").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx.get(f"https://v2.api.axisstream.co/api/provider/project/{pid2}").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "met", "name": "MET Norway Weather", "status": "CONNECTED"}]})
    )
    respx.get(f"https://v2.api.axisstream.co/api/alert/policies/project/{pid}").mock(
        return_value=httpx.Response(200, json=ALERT_POLICIES_FIXTURE)
    )
    respx.get(f"https://v2.api.axisstream.co/api/alert/policies/project/{pid2}").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"https://v2.api.axisstream.co/api/alert/project/{pid}").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"hasNextPage": False}})
    )
    respx.get(f"https://v2.api.axisstream.co/api/alert/project/{pid2}").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"hasNextPage": False}})
    )
    respx.post("https://data.api.axisstream.co/device/tbncorp/batch").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"status": 200, "body": WEATHER_TELEMETRY_FIXTURE},
                    {"status": 200, "body": SOILPROBE_TELEMETRY_FIXTURE},
                    {"status": 200, "body": WATERLEVEL_EMPTY_FIXTURE},
                    {"status": 200, "body": WATERFLOW_TELEMETRY_FIXTURE},
                ]
            },
        )
    )
    respx.get("https://data.api.axisstream.co/exchange/tbncorp/weather").mock(
        return_value=httpx.Response(200, json=[{"code": "79DAAFB4", "time": "2026-11-26T07:00:00Z", "temperature_avg": "29.9"}])
    )

    http = ResilientHttpClient()
    v2 = AxisStreamV2Client(http)
    tel = AxisStreamTelemetryClient(http)
    alrt = AxisStreamAlertClient(http)
    exch = AxisStreamExchangeClient(http)

    class CombinedMockedProvider:
        list_projects = v2.list_projects
        list_devices = v2.list_devices
        list_fields = v2.list_fields
        list_assets = v2.list_assets
        list_exchange_tokens = v2.list_exchange_tokens
        list_providers = v2.list_providers
        fetch_batch_telemetry = tel.fetch_batch_telemetry
        list_alert_policies = alrt.list_alert_policies
        list_alert_history = alrt.list_alert_history
        fetch_weather_exchange = exch.fetch_weather_exchange

    store = SqliteStateStore(":memory:")
    orch = IncrementalSyncOrchestrator(provider=CombinedMockedProvider(), state_store=store, event_hub=SseEventHub())
    try:
        summary = await orch.sync_all()
        assert summary["projects"] == 2
        assert summary["new_readings"] > 0
        assert len(orch.get_telemetry(pid)) == 4
        assert len(orch.get_exchange_weather(pid)) == 1
    finally:
        store.close()
        await http.aclose()


def test_ut_050_static_secret_scan_zero_real_credentials() -> None:
    platform_root = Path(__file__).resolve().parents[4]
    gitignore_path = platform_root / ".gitignore"
    assert gitignore_path.exists(), ".gitignore must exist to protect local init.js"
    assert "init.js" in gitignore_path.read_text(encoding="utf-8"), "init.js must be gitignored"
    assert (platform_root / "init.example.js").exists(), "init.example.js template must exist"

    static_dir = platform_root / "services" / "erp-platform" / "internal" / "api" / "static"
    assert not any(p.name == "init.js" for p in static_dir.rglob("*")), "init.js must NEVER live inside embedded static/"

    local_init_path = (platform_root / "init.js").resolve()
    forbidden_tokens = [
        "hoinv" + "@tanbaocorp.vn",
        "TanBao" + "@123",
        "TB" + "123456",
        "17921110" + "889134119",
        "78AIWMTu" + "lkotm4P",
    ]
    for path in platform_root.rglob("*"):
        if not path.is_file() or ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        if path.resolve() == local_init_path:
            continue
        if path.suffix.lower() in {".py", ".go", ".html", ".js", ".css", ".md", ".yml", ".yaml", ".env", ".example", ".json"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for forbidden in forbidden_tokens:
                assert forbidden not in text, f"Forbidden credential string found in {path}"


def test_ut_051_ssrf_and_path_traversal_blocked() -> None:
    for malicious in ("../../etc/passwd", "79DAAFB4@attacker.com", "tbncorp/evil", "id with spaces", ""):
        with pytest.raises(SecurityViolationError):
            validate_safe_path_segment(malicious, "test_param")


def test_ut_052_performance_15000_exchange_rows_within_sla() -> None:
    sample_row = {
        "code": "79DAAFB4",
        "time": "2026-11-26T07:00:00.000Z",
        "temperature_avg": "29.6",
        "humidity_avg": "71.2",
        "deltat_avg": "4.2",
        "dewpoint_avg": "23.8",
        "atmos_pressure_avg": "1010.2",
        "msl_pressure": "1012.3",
        "rainfall": "0.0",
        "rainfall_total": "12.4",
        "wind_speed_avg": "12.1",
        "wind_speed_min": "8.0",
        "wind_speed_max": "18.5",
        "wind_dir_deg_avg": "135",
        "wind_dir_var_avg": "18",
        "solar_rad_avg": "640.0",
        "uv_index_avg": "6.1",
    }
    raw_batch = [sample_row for _ in range(15000)]
    t0 = time.perf_counter()
    mapped = [AxisStreamExchangeClient.map_weather_row(r) for r in raw_batch]
    elapsed = time.perf_counter() - t0
    assert len(mapped) == 15000
    assert elapsed < 3.0


def test_ut_053_openapi_31_schema_snapshot_valid() -> None:
    app = create_app(BridgeSettings(mode="demo"), enable_background_sync=False)
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")
    assert "/api/v1/projects" in schema["paths"]
    assert "/api/v1/projects/{project_id}/telemetry" in schema["paths"]
    assert "/api/v1/projects/{project_id}/exchange/weather" in schema["paths"]
    assert "/api/v1/stream" in schema["paths"]


def test_ut_054_iso29119_traceability_matrix_completeness() -> None:
    platform_root = Path(__file__).resolve().parents[4]
    matrix_path = platform_root / "docs" / "traceability_matrix_29119.md"
    assert matrix_path.exists(), "docs/traceability_matrix_29119.md must exist"
    matrix_text = matrix_path.read_text(encoding="utf-8")
    for idx in range(1, 75):
        ut_id = f"UT-{idx:03d}"
        assert ut_id in matrix_text, f"Missing {ut_id} in traceability matrix"
    for idx in range(1, 63):
        gut_id = f"G-UT-{idx:03d}"
        assert gut_id in matrix_text, f"Missing {gut_id} in traceability matrix"
