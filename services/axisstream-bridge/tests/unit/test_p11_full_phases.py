"""AxisTech ISO Security, Encryption, 24h History & Resilience Tests (UT-063 to UT-070)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import httpx
import pytest
import respx

from axisstream_bridge.application.live_provider import LiveAxisStreamProvider
from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import SecurityViolationError
from axisstream_bridge.domain.models import TelemetryReading
from axisstream_bridge.infrastructure.security.crypto import FieldEncryptor
from axisstream_bridge.infrastructure.storage.state_store import SqliteStateStore
from axisstream_bridge.interfaces.api.app import create_app


def test_ut_063_aead_field_encryptor_roundtrip_and_tamper_rejection() -> None:
    enc = FieldEncryptor("test-axis-encryption-key")
    assert enc.enabled is True
    assert enc.algorithm == "HKDF-SHA256-CTR-HMAC-SHA256"

    plaintext = '{"device":"79DAAFB4","metric":"temperature","value":29.5}'
    token = enc.encrypt_text(plaintext)
    assert token.startswith("ENC:v1:")
    assert "79DAAFB4" not in token
    assert enc.decrypt_text(token) == plaintext

    wrong_key = FieldEncryptor("wrong-key")
    with pytest.raises(SecurityViolationError):
        wrong_key.decrypt_text(token)

    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(SecurityViolationError):
        enc.decrypt_text(tampered)

    passthrough = FieldEncryptor("")
    assert passthrough.enabled is False
    assert passthrough.encrypt_text(plaintext) == plaintext
    assert passthrough.decrypt_text(plaintext) == plaintext


def test_ut_064_encrypted_sqlite_outbox_at_rest(tmp_path: Path) -> None:
    db_file = tmp_path / "encrypted_bridge.db"
    store = SqliteStateStore(str(db_file), encryption_key="sqlite-outbox-master-key")
    assert store.encryption_enabled is True
    payload = {"project_id": "p-sec", "secret_note": "top-secret-field-telemetry"}
    store.enqueue_outbox("evt-1", "telemetry_update", payload)

    raw_conn = sqlite3.connect(str(db_file))
    row = raw_conn.execute("SELECT payload_json FROM outbox_events WHERE event_id = 'evt-1'").fetchone()
    raw_conn.close()
    assert row is not None
    assert str(row[0]).startswith("ENC:v1:")
    assert "top-secret-field-telemetry" not in str(row[0])

    pending = store.list_pending_outbox()
    store.close()
    assert len(pending) == 1
    assert pending[0]["payload"]["secret_note"] == "top-secret-field-telemetry"

    wrong_store = SqliteStateStore(str(db_file), encryption_key="incorrect-master-key")
    with pytest.raises(SecurityViolationError):
        wrong_store.list_pending_outbox()
    wrong_store.close()


def test_ut_065_sqlite_telemetry_history_persistence_and_route() -> None:
    store = SqliteStateStore(":memory:")
    now = datetime.now(timezone.utc)
    readings = [
        TelemetryReading(
            device_id="dev-1",
            external_id="79DAAFB4",
            source_code="weather",
            metric="temperature",
            value=29.5,
            unit="°C",
            timestamp_utc=now - timedelta(hours=2),
        ),
        TelemetryReading(
            device_id="dev-1",
            external_id="79DAAFB4",
            source_code="weather",
            metric="temperature",
            value=30.2,
            unit="°C",
            timestamp_utc=now - timedelta(hours=1),
        ),
    ]
    saved = store.save_telemetry_readings("proj-1", readings)
    assert saved == 2

    hist_dev1 = store.query_telemetry_history("proj-1", device_id="dev-1", hours=24)
    assert len(hist_dev1) == 2
    assert hist_dev1[0]["value"] == 29.5
    assert hist_dev1[1]["value"] == 30.2
    store.close()

    settings = BridgeSettings(mode="demo", inbound_api_key="test-key-hist")
    app = create_app(settings, enable_background_sync=False)
    with TestClient(app) as client:
        projs = client.get("/api/v1/projects", headers={"X-API-Key": "test-key-hist"}).json()["data"]
        pid = projs[0]["id"]
        resp = client.get(f"/api/v1/projects/{pid}/telemetry/history?hours=24", headers={"X-API-Key": "test-key-hist"})
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1


def test_ut_066_security_posture_endpoint_and_hsts_headers() -> None:
    settings = BridgeSettings(
        mode="demo",
        inbound_api_key="posture-api-key",
        webhook_secret="webhook-hmac-secret",
        encryption_key="bridge-aead-key",
    )
    app = create_app(settings, enable_background_sync=False)
    with TestClient(app) as client:
        resp = client.get("/api/v1/security/posture", headers={"X-API-Key": "posture-api-key"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["encryption_at_rest"] is True
        assert body["encryption_algorithm"] == "HKDF-SHA256-CTR-HMAC-SHA256"
        assert body["tls_strict_host_suffix"] == ".axisstream.co"
        assert body["read_only_sync"] is True
        assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
        assert "camera=()" in resp.headers["Permissions-Policy"]


@respx.mock
async def test_ut_067_live_provider_resilience_fallbacks_and_degraded_branches() -> None:
    respx.post("https://v2.api.axisstream.co/api/account/login").mock(
        return_value=httpx.Response(200, json={"ok": True}, headers={"set-cookie": "connect.sid=fake-sid; Path=/"})
    )
    respx.get("https://v2.api.axisstream.co/api/project/list").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "p-live",
                        "name": "Demo",
                        "organisation": {"id": "o1", "name": "Org", "schema": "tbncorp"},
                    }
                ]
            },
        )
    )
    respx.get("https://v2.api.axisstream.co/api/device/project/p-live").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "d1", "name": "WS", "externalId": "79DAAFB4", "sourceCode": "weather", "active": True},
                    {"id": "d2", "name": "Broken", "externalId": "BROKEN01", "sourceCode": "waterlevel", "active": True},
                ],
                "meta": {"hasNextPage": False},
            },
        )
    )
    respx.get("https://v2.api.axisstream.co/api/field/project/p-live").mock(return_value=httpx.Response(500))
    respx.get("https://v2.api.axisstream.co/api/asset/project/p-live").mock(return_value=httpx.Response(500))
    respx.get("https://v2.api.axisstream.co/api/alert/policies/project/p-live").mock(return_value=httpx.Response(500))
    respx.get("https://v2.api.axisstream.co/api/alert/project/p-live").mock(return_value=httpx.Response(500))
    respx.get("https://v2.api.axisstream.co/api/exchange/project/p-live").mock(return_value=httpx.Response(500))

    respx.post("https://data.api.axisstream.co/device/tbncorp/batch").mock(return_value=httpx.Response(500))
    respx.get("https://data.api.axisstream.co/device/tbncorp/weather/79DAAFB4/device").mock(
        return_value=httpx.Response(
            200,
            json={
                "recentData": {"temperature": "28.4", "humidity": "75.0", "time": "2026-11-26T08:00:00Z"}
            },
        )
    )
    respx.get("https://data.api.axisstream.co/device/tbncorp/waterlevel/BROKEN01/device").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://data.api.axisstream.co/exchange/tbncorp/weather").mock(return_value=httpx.Response(500))

    respx.get("https://v2.api.axisstream.co/api/provider/project/p-live").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "met-1", "name": "MET Norway Weather", "code": "metnorway", "status": "CONNECTED"},
                    {"id": "janes-1", "name": "Jane's Weather", "code": "janesweather", "status": "CONNECTED"},
                ]
            },
        )
    )
    respx.get("https://provider.api.axisstream.co/metnorway/forecast/project/p-live/provider/met-1").mock(
        return_value=httpx.Response(200, json={"location": {"name": "Farm"}, "days": [], "steps": []})
    )
    respx.get("https://provider.api.axisstream.co/janes_weather/forecast/project/p-live/provider/janes-1").mock(
        return_value=httpx.Response(200, json={"spray": {"windows": []}})
    )

    settings = BridgeSettings(
        mode="live",
        auth_mode="cookie",
        axisstream_username="tester",
        axisstream_password="secret",
        max_retries=0,
        circuit_failure_threshold=20,
    )
    lp = LiveAxisStreamProvider(settings)
    try:
        projs = await lp.list_projects()
        assert len(projs) == 1
        devs = await lp.list_devices("p-live")
        assert len(devs) == 2
        assert await lp.list_fields("p-live") == []
        assert await lp.list_assets("p-live") == []
        assert await lp.list_alert_policies("p-live") == []
        assert await lp.list_alert_history("p-live") == []
        assert await lp.list_exchange_tokens("p-live") == []

        batch = await lp.fetch_batch_telemetry("tbncorp", devs, date(2026, 11, 26), date(2026, 11, 26))
        assert len(batch.snapshots) == 1
        assert len(batch.errors) == 1

        derived = await lp.fetch_weather_exchange("tbncorp", "p-live")
        assert len(derived) == 1
        assert derived[0].temperature_avg == 28.4

        fc = await lp.fetch_project_forecast("p-live")
        assert fc.met_norway.status == "CONNECTED"
        assert fc.janes_weather.status == "CONNECTED"
    finally:
        await lp.aclose()


async def test_ut_068_axisstream_dual_exchange_token_auth_wiring() -> None:
    settings = BridgeSettings(
        mode="live",
        auth_mode="dual",
        axisstream_username="u",
        axisstream_password="p",
        axisstream_exchange_token="dummy-exchange-token-only",
    )
    lp = LiveAxisStreamProvider(settings)
    assert lp._exchange_http is not None
    assert lp._exchange._http is lp._exchange_http
    await lp.aclose()


def test_ut_069_single_module_scope_and_secret_masking() -> None:
    settings = BridgeSettings(
        mode="demo",
        encryption_key="MY_SUPER_SECRET_AES_KEY_XYZ",
        axisstream_password="MY_SECRET_PASSWORD_123",
    )
    masked = f"{settings!r} {settings!s}"
    assert "MY_SUPER_SECRET_AES_KEY_XYZ" not in masked
    assert "MY_SECRET_PASSWORD_123" not in masked

    legacy_tok_1 = "xiao" + "ma"
    legacy_tok_2 = "multi_" + "vendor"
    platform_root = Path(__file__).resolve().parents[4]
    for folder in ("services", "docs"):
        for path in (platform_root / folder).rglob("*"):
            if not path.is_file() or any(p in path.parts for p in (".venv", "__pycache__", ".gocache", ".gopath")):
                continue
            if path.suffix.lower() in {".py", ".go", ".html", ".js", ".css", ".md"}:
                lower = path.read_text(encoding="utf-8", errors="ignore").lower()
                assert legacy_tok_1 not in lower, f"Removed vendor reference found in {path}"
                assert legacy_tok_2 not in lower, f"Removed multi-vendor reference found in {path}"


def test_ut_070_persistent_sqlite_history_survives_reopen(tmp_path: Path) -> None:
    db_file = tmp_path / "persist_history.db"
    s1 = SqliteStateStore(str(db_file))
    ts = datetime.now(timezone.utc) - timedelta(hours=1)
    s1.save_telemetry_readings(
        "p-persist",
        [
            TelemetryReading(
                device_id="d-persist",
                external_id="EXT1",
                source_code="soilprobe",
                metric="ph",
                value=6.9,
                unit="pH",
                depth_level=1,
                timestamp_utc=ts,
            )
        ],
    )
    s1.close()

    s2 = SqliteStateStore(str(db_file))
    reloaded = s2.query_telemetry_history("p-persist", device_id="d-persist", hours=24)
    s2.close()
    assert len(reloaded) == 1
    assert reloaded[0]["metric"] == "ph"
    assert reloaded[0]["value"] == 6.9
