"""Prompt 6 Unit Tests (UT-036 to UT-041): Alerts, Incremental Cursor, Idempotency, Outbox/DLQ."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from axisstream_bridge.application.demo_provider import DemoAxisStreamProvider
from axisstream_bridge.application.sync_service import (
    IncrementalSyncOrchestrator,
    SseEventHub,
)
from axisstream_bridge.core.exceptions import UpstreamTransientError
from axisstream_bridge.infrastructure.axisstream.alert_client import AxisStreamAlertClient
from axisstream_bridge.infrastructure.http.client import ResilientHttpClient
from axisstream_bridge.infrastructure.storage.state_store import (
    SqliteStateStore,
    compute_dedup_key,
)
from tests.fixtures.axisstream_fixtures import ALERT_POLICIES_FIXTURE, ALERT_TEMPLATES_FIXTURE


@respx.mock
async def test_ut_036_alert_policies_and_templates_mapping() -> None:
    respx.get("https://v2.api.axisstream.co/api/alert/templates").mock(
        return_value=httpx.Response(200, json=ALERT_TEMPLATES_FIXTURE)
    )
    respx.get("https://v2.api.axisstream.co/api/alert/policies/project/proj-1").mock(
        return_value=httpx.Response(200, json=ALERT_POLICIES_FIXTURE)
    )
    http = ResilientHttpClient()
    client = AxisStreamAlertClient(http)
    try:
        tpls = await client.list_alert_templates()
        assert len(tpls[0]["policy"]["operators"]) == 8
        pols = await client.list_alert_policies("proj-1")
        assert pols[0].name == "Strong wind alert"
        assert pols[0].status == "PAUSED"
        assert pols[0].conditions[0].operator == ">="
        assert pols[0].conditions[0].threshold == "20"
    finally:
        await http.aclose()


def test_ut_037_idempotency_deduplication_key() -> None:
    store = SqliteStateStore(":memory:")
    ts = datetime(2026, 11, 26, 7, 0, 0, tzinfo=timezone.utc)
    k = compute_dedup_key("tbncorp", "dev-1", "temperature", ts)
    assert store.check_and_record_dedup(k) is True
    assert store.check_and_record_dedup(k) is False
    store.close()


async def test_ut_038_incremental_cursor_rollback_safe_on_failure() -> None:
    store = SqliteStateStore(":memory:")
    hub = SseEventHub()
    demo = DemoAxisStreamProvider()
    orch = IncrementalSyncOrchestrator(provider=demo, state_store=store, event_hub=hub)
    await orch.sync_all()
    first_cursor = store.get_cursor("telemetry:1b73e2fe-1e6c-46c6-8534-82c0e03be283")
    assert first_cursor is not None

    class FailingProvider(DemoAxisStreamProvider):
        async def fetch_batch_telemetry(self, *args, **kwargs):
            raise UpstreamTransientError("Upstream down mid-sync")

    orch_fail = IncrementalSyncOrchestrator(provider=FailingProvider(), state_store=store, event_hub=hub)
    with pytest.raises(UpstreamTransientError):
        await orch_fail.sync_all()
    assert store.get_cursor("telemetry:1b73e2fe-1e6c-46c6-8534-82c0e03be283") == first_cursor
    store.close()


def test_ut_039_outbox_retry_and_dead_letter_queue() -> None:
    store = SqliteStateStore(":memory:")
    store.enqueue_outbox("evt-1", "telemetry_update", {"k": 1})
    store.enqueue_outbox("evt-2", "telemetry_update", {"k": 2})

    assert len(store.list_pending_outbox()) == 2
    assert store.mark_outbox_failed("evt-1", "timeout 1", max_attempts=3) == "PENDING"
    assert store.mark_outbox_failed("evt-1", "timeout 2", max_attempts=3) == "PENDING"
    assert store.mark_outbox_failed("evt-1", "timeout 3", max_attempts=3) == "DEAD_LETTER"

    ev1 = store.get_outbox_event("evt-1")
    assert ev1 is not None and ev1["status"] == "DEAD_LETTER"

    store.mark_outbox_delivered("evt-2")
    assert store.list_pending_outbox() == []
    store.close()


def test_ut_040_sqlite_persistence_survives_restart(tmp_path: Path) -> None:
    db_file = str(tmp_path / "bridge_state.db")
    ts = datetime(2026, 11, 26, 7, 15, 0, tzinfo=timezone.utc)
    s1 = SqliteStateStore(db_file)
    s1.set_cursor("telemetry:proj-1", ts)
    s1.enqueue_outbox("evt-persist", "alert_update", {"a": 42})
    s1.close()

    s2 = SqliteStateStore(db_file)
    assert s2.get_cursor("telemetry:proj-1") == ts
    pending = s2.list_pending_outbox()
    assert len(pending) == 1 and pending[0]["event_id"] == "evt-persist"
    s2.close()


@respx.mock
async def test_ut_041_empty_alert_history_body_handled_safely() -> None:
    respx.get("https://v2.api.axisstream.co/api/alert/project/proj-tbsg").mock(
        return_value=httpx.Response(200, content=b"")
    )
    http = ResilientHttpClient()
    client = AxisStreamAlertClient(http)
    try:
        items = await client.list_alert_history("proj-tbsg")
        assert items == []
    finally:
        await http.aclose()
