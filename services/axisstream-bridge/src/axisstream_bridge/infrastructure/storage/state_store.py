"""SQLite / In-Memory State Store: Watermark Cursors, SHA-256 Deduplication, Outbox & DLQ."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import threading
from typing import Any

from axisstream_bridge.domain.normalizers import parse_iso_timestamp
from axisstream_bridge.infrastructure.security.crypto import FieldEncryptor


def compute_dedup_key(
    org_code: str, device_id: str, metric: str, timestamp_utc: datetime, depth_level: int | None = None
) -> str:
    """Compute deterministic SHA-256 deduplication key for a telemetry sample."""
    raw = f"{org_code}|{device_id}|{metric}|{depth_level or 0}|{timestamp_utc.astimezone(timezone.utc).isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SqliteStateStore:
    """Thread-safe SQLite store implementing StateStorePort."""

    def __init__(self, db_path: str = ":memory:", *, encryption_key: str = "") -> None:
        self.db_path = db_path
        self._encryptor = FieldEncryptor(encryption_key)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_cursors (
                    scope_key TEXT PRIMARY KEY,
                    cursor_utc TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dedup_keys (
                    dedup_hash TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_history (
                    project_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    source_code TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    depth_level INTEGER NOT NULL DEFAULT 0,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL DEFAULT '',
                    timestamp_utc TEXT NOT NULL,
                    PRIMARY KEY (device_id, metric, depth_level, timestamp_utc)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tel_hist_proj_dev_ts
                ON telemetry_history(project_id, device_id, timestamp_utc)
                """
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def is_healthy(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def get_cursor(self, scope_key: str) -> datetime | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT cursor_utc FROM sync_cursors WHERE scope_key = ?", (scope_key,)
            ).fetchone()
        if row is None:
            return None
        return parse_iso_timestamp(row["cursor_utc"])

    def set_cursor(self, scope_key: str, cursor_utc: datetime) -> None:
        now = datetime.now(timezone.utc).isoformat()
        val = cursor_utc.astimezone(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO sync_cursors(scope_key, cursor_utc, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    cursor_utc = excluded.cursor_utc,
                    updated_at = excluded.updated_at
                """,
                (scope_key, val, now),
            )

    def check_and_record_dedup(self, dedup_key: str) -> bool:
        """Return True if key is NEW and recorded; False if duplicate."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO dedup_keys(dedup_hash, created_at) VALUES (?, ?)",
                (dedup_key, now),
            )
            return cur.rowcount == 1

    @property
    def encryption_enabled(self) -> bool:
        return self._encryptor.enabled

    @property
    def encryption_algorithm(self) -> str:
        return self._encryptor.algorithm

    def enqueue_outbox(self, event_id: str, event_type: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload_raw = json.dumps(payload, ensure_ascii=False, default=str)
        payload_stored = self._encryptor.encrypt_text(payload_raw)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO outbox_events(
                    event_id, event_type, payload_json, status, retry_count, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, 'PENDING', 0, '', ?, ?)
                """,
                (event_id, event_type, payload_stored, now, now),
            )

    def list_pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, event_type, payload_json, status, retry_count, last_error, created_at, updated_at
                FROM outbox_events
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "event_id": r["event_id"],
                "event_type": r["event_type"],
                "payload": json.loads(self._encryptor.decrypt_text(r["payload_json"])),
                "status": r["status"],
                "retry_count": r["retry_count"],
                "last_error": r["last_error"],
            }
            for r in rows
        ]

    def get_outbox_event(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if r is None:
            return None
        row_dict = dict(r)
        row_dict["payload_json"] = self._encryptor.decrypt_text(row_dict["payload_json"])
        return row_dict

    def mark_outbox_delivered(self, event_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbox_events SET status = 'DELIVERED', updated_at = ? WHERE event_id = ?",
                (now, event_id),
            )

    def mark_outbox_failed(self, event_id: str, error: str, max_attempts: int = 3) -> str:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT retry_count FROM outbox_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            next_count = (row["retry_count"] if row else 0) + 1
            new_status = "DEAD_LETTER" if next_count >= max_attempts else "PENDING"
            self._conn.execute(
                """
                UPDATE outbox_events
                SET retry_count = ?, status = ?, last_error = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (next_count, new_status, error[:500], now, event_id),
            )
            return new_status

    def save_telemetry_readings(self, project_id: str, readings: list[Any]) -> int:
        """Persist canonical TelemetryReading rows into SQLite telemetry_history."""
        rows_to_insert: list[tuple[Any, ...]] = []
        for r in readings or []:
            val = getattr(r, "value", None)
            ts = getattr(r, "timestamp_utc", None)
            if val is None or ts is None:
                continue
            depth = getattr(r, "depth_level", None)
            ts_iso = ts.astimezone(timezone.utc).isoformat() if isinstance(ts, datetime) else str(ts)
            rows_to_insert.append(
                (
                    project_id,
                    str(getattr(r, "device_id", "")),
                    str(getattr(r, "external_id", "")),
                    str(getattr(r, "source_code", "")),
                    str(getattr(r, "metric", "")),
                    int(depth) if depth is not None else 0,
                    float(val),
                    str(getattr(r, "unit", "") or ""),
                    ts_iso,
                )
            )
        if not rows_to_insert:
            return 0
        with self._lock, self._conn:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO telemetry_history(
                    project_id, device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        return len(rows_to_insert)

    def query_telemetry_history(
        self,
        project_id: str,
        device_id: str | None = None,
        hours: int = 24,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Query persisted telemetry history ordered chronologically; falls back to latest stored rows."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))).isoformat()
        with self._lock:
            if device_id:
                rows = self._conn.execute(
                    """
                    SELECT device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                    FROM telemetry_history
                    WHERE project_id = ? AND device_id = ? AND timestamp_utc >= ?
                    ORDER BY timestamp_utc ASC
                    LIMIT ?
                    """,
                    (project_id, device_id, cutoff, limit),
                ).fetchall()
                if not rows:
                    rows = self._conn.execute(
                        """
                        SELECT device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                        FROM (
                            SELECT device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                            FROM telemetry_history
                            WHERE project_id = ? AND device_id = ?
                            ORDER BY timestamp_utc DESC
                            LIMIT ?
                        ) sub
                        ORDER BY timestamp_utc ASC
                        """,
                        (project_id, device_id, limit),
                    ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                    FROM telemetry_history
                    WHERE project_id = ? AND timestamp_utc >= ?
                    ORDER BY timestamp_utc ASC
                    LIMIT ?
                    """,
                    (project_id, cutoff, limit),
                ).fetchall()
                if not rows:
                    rows = self._conn.execute(
                        """
                        SELECT device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                        FROM (
                            SELECT device_id, external_id, source_code, metric, depth_level, value, unit, timestamp_utc
                            FROM telemetry_history
                            WHERE project_id = ?
                            ORDER BY timestamp_utc DESC
                            LIMIT ?
                        ) sub
                        ORDER BY timestamp_utc ASC
                        """,
                        (project_id, limit),
                    ).fetchall()
        return [
            {
                "device_id": r["device_id"],
                "external_id": r["external_id"],
                "source_code": r["source_code"],
                "metric": r["metric"],
                "value": r["value"],
                "unit": r["unit"],
                "depth_level": int(r["depth_level"]) if int(r["depth_level"]) > 0 else None,
                "timestamp_utc": r["timestamp_utc"],
            }
            for r in rows
        ]
