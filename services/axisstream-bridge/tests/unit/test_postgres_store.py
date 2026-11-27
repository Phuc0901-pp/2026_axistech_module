"""ISO PostgreSQL 16 Migration Contract & PostgresStateStore Unit Tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.infrastructure.storage.postgres_store import PostgresStateStore


class _FakeCursor:
    def __init__(self, state: dict) -> None:
        self._state = state
        self._rows: list[tuple] = []
        self.rowcount = 0

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        norm = " ".join(sql.split()).upper()
        self._rows = []
        self.rowcount = 0
        if norm.startswith("SELECT 1"):
            self._rows = [(1,)]
        elif "INSERT INTO OPS.SYNC_CURSORS" in norm:
            scope, cursor_utc = params[0], params[1]
            self._state["cursors"][scope] = cursor_utc
            self.rowcount = 1
        elif "SELECT CURSOR_UTC FROM OPS.SYNC_CURSORS" in norm:
            val = self._state["cursors"].get(params[0])
            if val is not None:
                self._rows = [(val,)]
        elif "INSERT INTO OPS.DEDUP_KEYS" in norm:
            key = params[0]
            if key not in self._state["dedup"]:
                self._state["dedup"].add(key)
                self.rowcount = 1
        elif "INSERT INTO OPS.OUTBOX_EVENTS" in norm:
            eid, etype, enc = params[0], params[1], params[2]
            if eid not in self._state["outbox"]:
                now = datetime.now(timezone.utc)
                self._state["outbox"][eid] = {
                    "event_id": eid,
                    "event_type": etype,
                    "payload_encrypted": enc,
                    "status": "PENDING",
                    "retry_count": 0,
                    "last_error": "",
                    "created_at": now,
                    "updated_at": now,
                }
                self.rowcount = 1
        elif "FROM OPS.OUTBOX_EVENTS WHERE STATUS = 'PENDING'" in norm:
            self._rows = [
                (
                    r["event_id"],
                    r["event_type"],
                    r["payload_encrypted"],
                    r["status"],
                    r["retry_count"],
                    r["last_error"],
                )
                for r in self._state["outbox"].values()
                if r["status"] == "PENDING"
            ][: int(params[0])]
        elif "FROM OPS.OUTBOX_EVENTS WHERE EVENT_ID" in norm and "SELECT EVENT_ID" in norm:
            r = self._state["outbox"].get(params[0])
            if r:
                self._rows = [
                    (
                        r["event_id"],
                        r["event_type"],
                        r["payload_encrypted"],
                        r["status"],
                        r["retry_count"],
                        r["last_error"],
                        r["created_at"],
                        r["updated_at"],
                    )
                ]
        elif "SELECT RETRY_COUNT FROM OPS.OUTBOX_EVENTS" in norm:
            r = self._state["outbox"].get(params[0])
            if r:
                self._rows = [(r["retry_count"],)]
        elif "UPDATE OPS.OUTBOX_EVENTS SET STATUS = 'DELIVERED'" in norm:
            r = self._state["outbox"].get(params[0])
            if r:
                r["status"] = "DELIVERED"
        elif "UPDATE OPS.OUTBOX_EVENTS SET RETRY_COUNT" in norm:
            next_c, st, err, eid = params
            r = self._state["outbox"].get(eid)
            if r:
                r["retry_count"] = next_c
                r["status"] = st
                r["last_error"] = err
        elif "FROM TELEMETRY.READINGS" in norm:
            proj_id = params[0]
            rows = [r for r in self._state["readings"].values() if r[0] == proj_id]
            self._rows = [(r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]) for r in rows]

    def executemany(self, _sql: str, rows: list[tuple]) -> None:
        for row in rows:
            pk = (row[1], row[4], row[5], row[8])
            self._state["readings"][pk] = row

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, state: dict) -> None:
        self._state = state

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._state)

    def commit(self) -> None:
        return None


class _FakePool:
    def __init__(self) -> None:
        self.state = {"cursors": {}, "dedup": set(), "outbox": {}, "readings": {}}

    def connection(self) -> _FakeConn:
        return _FakeConn(self.state)


def test_ut_072_iso_postgres_migrations_complete() -> None:
    root = Path(__file__).resolve().parents[4]
    mig_dir = root / "db" / "migrations"
    sql_001 = (mig_dir / "001_iso_schema.sql").read_text(encoding="utf-8")
    sql_002 = (mig_dir / "002_indexes_and_partitions.sql").read_text(encoding="utf-8")
    sql_003 = (mig_dir / "003_security_rls_and_audit_immutability.sql").read_text(encoding="utf-8")
    sql_004 = (mig_dir / "004_seed_metric_catalog_vi.sql").read_text(encoding="utf-8")

    for schema in ("core", "telemetry", "ops", "compliance"):
        assert f"CREATE SCHEMA IF NOT EXISTS {schema}" in sql_001
    assert "PARTITION BY RANGE (timestamp_utc)" in sql_001
    assert "1971-01-01T00:00:00Z" in sql_001
    assert "telemetry.ensure_monthly_partition" in sql_002
    assert "USING brin (timestamp_utc)" in sql_002
    assert "trg_compliance_audit_immutable" in sql_003
    assert "ENABLE ROW LEVEL SECURITY" in sql_003
    assert "Nhiệt độ không khí" in sql_004
    assert "Áp suất khí quyển tại trạm" in sql_004


def test_ut_073_postgres_state_store_contracts_and_aead(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "TbsgAgtech_db")
    monkeypatch.setenv("POSTGRES_USER", "agtech_admin")
    monkeypatch.setenv("POSTGRES_PASSWORD", "Test@Pass123")
    cfg = BridgeSettings(mode="demo")
    assembled = cfg.resolved_database_url()
    assert assembled == "postgresql://agtech_admin:Test%40Pass123@postgres:5432/TbsgAgtech_db"
    assert "Test@Pass123" not in repr(cfg)

    monkeypatch.setenv("AXISSTREAM_DATABASE_URL", "postgresql://agtech:secret@postgres:5432/TbsgAgtech_db")
    cfg2 = BridgeSettings(mode="demo")
    assert cfg2.resolved_database_url().startswith("postgresql://")
    assert "secret" not in str(cfg2.database_url)

    pool = _FakePool()
    store = PostgresStateStore(
        "postgresql://agtech:secret@postgres:5432/axistech_erp",
        encryption_key="unit-test-aead-key-material",
        pool=pool,
    )
    assert store.is_healthy()
    assert store.encryption_enabled

    ts = datetime(2026, 11, 27, 8, 0, tzinfo=timezone.utc)
    store.set_cursor("proj-1", ts)
    assert store.get_cursor("proj-1") == ts

    assert store.check_and_record_dedup("hash-1") is True
    assert store.check_and_record_dedup("hash-1") is False

    store.enqueue_outbox("evt-1", "sync_update", {"station": "A23", "temp": 29.5})
    assert pool.state["outbox"]["evt-1"]["payload_encrypted"].startswith("ENC:v1:")
    pending = store.list_pending_outbox()
    assert len(pending) == 1 and pending[0]["payload"]["station"] == "A23"
    assert store.mark_outbox_failed("evt-1", "timeout", max_attempts=1) == "DLQ"

    readings = [
        SimpleNamespace(
            device_id="dev-1",
            external_id="EXT1",
            source_code="weather",
            metric="temperature",
            depth_level=None,
            value=29.5,
            unit="°C",
            timestamp_utc=ts,
        ),
        SimpleNamespace(
            device_id="dev-1",
            external_id="EXT1",
            source_code="weather",
            metric="temperature",
            depth_level=None,
            value=0.0,
            unit="°C",
            timestamp_utc=datetime(1970, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    saved = store.save_telemetry_readings("proj-1", readings)
    assert saved == 1
    hist = store.query_telemetry_history("proj-1", device_id="dev-1")
    assert len(hist) == 1 and hist[0]["metric"] == "temperature"
