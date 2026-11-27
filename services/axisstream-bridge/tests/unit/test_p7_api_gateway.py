"""Prompt 7 Unit Tests (UT-042 to UT-048): FastAPI Gateway, RFC 9457, HMAC Webhooks, Fail-Open."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

from axisstream_bridge.application.demo_provider import DEMO_PROJECT_TANBAO_ID
from axisstream_bridge.application.sync_service import FailOpenEnrichmentConsumer
from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import UpstreamTransientError
from axisstream_bridge.infrastructure.http.circuit_breaker import CircuitBreaker
from axisstream_bridge.interfaces.api.app import create_app
from axisstream_bridge.interfaces.api.webhooks import (
    sign_webhook_payload,
    verify_webhook_signature,
)


def _settings() -> BridgeSettings:
    return BridgeSettings(mode="demo", inbound_api_key="test-key-123")


def test_ut_042_inbound_api_key_auth_guard() -> None:
    app = create_app(_settings(), enable_background_sync=False)
    with TestClient(app) as client:
        r_missing = client.get("/api/v1/projects")
        assert r_missing.status_code == 401
        assert r_missing.headers["content-type"].startswith("application/problem+json")

        r_wrong = client.get("/api/v1/projects", headers={"X-API-Key": "wrong"})
        assert r_wrong.status_code == 401

        r_ok = client.get("/api/v1/projects", headers={"X-API-Key": "test-key-123"})
        assert r_ok.status_code == 200
        assert r_ok.json()["count"] == 2


def test_ut_043_api_endpoints_and_input_validation() -> None:
    app = create_app(_settings(), enable_background_sync=False)
    headers = {"X-API-Key": "test-key-123"}
    with TestClient(app) as client:
        assert client.get(f"/api/v1/projects/{DEMO_PROJECT_TANBAO_ID}/devices", headers=headers).json()["count"] == 4
        assert client.get(f"/api/v1/projects/{DEMO_PROJECT_TANBAO_ID}/telemetry", headers=headers).json()["count"] == 4
        assert client.get(f"/api/v1/projects/{DEMO_PROJECT_TANBAO_ID}/fields", headers=headers).json()["count"] == 2
        assert client.get(f"/api/v1/projects/{DEMO_PROJECT_TANBAO_ID}/assets", headers=headers).json()["count"] == 2
        assert client.get(f"/api/v1/projects/{DEMO_PROJECT_TANBAO_ID}/alerts/policies", headers=headers).json()["count"] == 3
        ex = client.get(f"/api/v1/projects/{DEMO_PROJECT_TANBAO_ID}/exchange/weather", headers=headers).json()
        assert len(ex["tokens"][0]["datasets"][0]["columns"]) == 17
        assert ex["count"] == 12


def test_ut_044_health_live_and_ready_circuit_breaker_probe() -> None:
    cb = CircuitBreaker(failure_threshold=1)
    app = create_app(_settings(), circuit_breaker=cb, enable_background_sync=False)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        cb.record_failure()
        r_down = client.get("/health/ready")
        assert r_down.status_code == 503
        assert r_down.json()["circuit_breaker"] == "OPEN"


def test_ut_045_rfc9457_problem_json_on_upstream_error() -> None:
    app = create_app(_settings(), enable_background_sync=False)

    async def broken_sync():
        raise UpstreamTransientError("Upstream gateway timed out")

    with TestClient(app) as client:
        app.state.orchestrator.sync_all = broken_sync  # type: ignore[method-assign]
        r = client.post(
            "/api/v1/sync/trigger",
            headers={"X-API-Key": "test-key-123", "X-Correlation-ID": "cid-502-test"},
        )
        assert r.status_code == 502
        body = r.json()
        assert body["title"] == "UPSTREAM_TRANSIENT_ERROR"
        assert body["correlation_id"] == "cid-502-test"
        assert "Traceback" not in r.text


def test_ut_046_webhook_hmac_sha256_signature_verification() -> None:
    payload = json.dumps({"event": "telemetry_update", "temp": 30.1}).encode("utf-8")
    sig = sign_webhook_payload(payload, "shared-webhook-secret")
    assert sig.startswith("sha256=")
    assert verify_webhook_signature(payload, "shared-webhook-secret", sig) is True
    tampered = payload.replace(b"30.1", b"99.9")
    assert verify_webhook_signature(tampered, "shared-webhook-secret", sig) is False


def test_ut_047_metrics_and_sync_trigger_facade() -> None:
    app = create_app(_settings(), enable_background_sync=False)
    headers = {"X-API-Key": "test-key-123"}
    with TestClient(app) as client:
        r1 = client.post("/api/v1/sync/trigger", headers=headers)
        assert r1.status_code == 200
        assert r1.json()["sync_count"] == 2
        m = client.get("/metrics").json()
        assert m["sync_count"] == 2
        assert m["projects_cached"] == 2


async def test_ut_048_fail_open_consumer_never_blocks_on_bridge_error() -> None:
    app = create_app(_settings(), enable_background_sync=False)
    orch = app.state.orchestrator

    def failing_get_telemetry(_pid: str):
        raise UpstreamTransientError("Simulated outage")

    orch.get_telemetry = failing_get_telemetry  # type: ignore[method-assign]
    consumer = FailOpenEnrichmentConsumer(orch)
    out = await consumer.enrich_record(DEMO_PROJECT_TANBAO_ID, {"eid": "000123456789012"})
    assert out["eid"] == "000123456789012"
    assert out["enrichment_status"] == "DEGRADED_FAIL_OPEN"
