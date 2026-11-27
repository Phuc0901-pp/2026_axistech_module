"""PostgreSQL 16 ISO State Store implementing ops.* and partitioned telemetry.readings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from axisstream_bridge.domain.normalizers import parse_iso_timestamp
from axisstream_bridge.infrastructure.security.crypto import FieldEncryptor


EPOCH_SENTINEL_CUTOFF = datetime(1971, 1, 1, tzinfo=timezone.utc)


class PostgresStateStore:
    """Thread-safe PostgreSQL connection-pooled store matching SqliteStateStore / StateStorePort."""

    def __init__(
        self,
        database_url: str,
        *,
        encryption_key: str = "",
        pool: Any | None = None,
        min_size: int = 1,
        max_size: int = 10,
    ) -> None:
        self.database_url = database_url
        self._encryptor = FieldEncryptor(encryption_key)
        self._owns_pool = pool is None
        if pool is not None:
            self._pool = pool
        else:
            from psycopg_pool import ConnectionPool

            self._pool = ConnectionPool(
                conninfo=database_url,
                min_size=min_size,
                max_size=max_size,
                open=True,
            )

    def close(self) -> None:
        if self._owns_pool and self._pool is not None and hasattr(self._pool, "close"):
            self._pool.close()

    def is_healthy(self) -> bool:
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True
        except Exception:
            return False

    @property
    def encryption_enabled(self) -> bool:
        return self._encryptor.enabled

    @property
    def encryption_algorithm(self) -> str:
        return self._encryptor.algorithm

    def get_cursor(self, scope_key: str) -> datetime | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cursor_utc FROM ops.sync_cursors WHERE scope_key = %s",
                    (scope_key,),
                )
                row = cur.fetchone()
        if not row or row[0] is None:
            return None
        val = row[0]
        if isinstance(val, datetime):
            return val.astimezone(timezone.utc) if val.tzinfo else val.replace(tzinfo=timezone.utc)
        return parse_iso_timestamp(str(val))

    def set_cursor(self, scope_key: str, cursor_utc: datetime) -> None:
        val = cursor_utc.astimezone(timezone.utc)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.sync_cursors (scope_key, cursor_utc, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (scope_key) DO UPDATE SET
                        cursor_utc = EXCLUDED.cursor_utc,
                        updated_at = now()
                    """,
                    (scope_key, val),
                )
            conn.commit()

    def check_and_record_dedup(self, dedup_key: str) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.dedup_keys (dedup_hash, created_at)
                    VALUES (%s, now())
                    ON CONFLICT (dedup_hash) DO NOTHING
                    """,
                    (dedup_key,),
                )
                inserted = cur.rowcount == 1
            conn.commit()
        return inserted

    def enqueue_outbox(self, event_id: str, event_type: str, payload: dict[str, Any]) -> None:
        payload_raw = json.dumps(payload, ensure_ascii=False, default=str)
        payload_stored = self._encryptor.encrypt_text(payload_raw)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.outbox_events (
                        event_id, event_type, payload_encrypted, status, retry_count, last_error, created_at, updated_at
                    ) VALUES (%s, %s, %s, 'PENDING', 0, '', now(), now())
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (event_id, event_type, payload_stored),
                )
            conn.commit()

    def list_pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, event_type, payload_encrypted, status, retry_count, last_error
                    FROM ops.outbox_events
                    WHERE status = 'PENDING'
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [
            {
                "event_id": r[0],
                "event_type": r[1],
                "payload": json.loads(self._encryptor.decrypt_text(r[2])),
                "status": r[3],
                "retry_count": r[4],
                "last_error": r[5],
            }
            for r in rows
        ]

    def get_outbox_event(self, event_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, event_type, payload_encrypted, status, retry_count, last_error, created_at, updated_at
                    FROM ops.outbox_events
                    WHERE event_id = %s
                    """,
                    (event_id,),
                )
                r = cur.fetchone()
        if r is None:
            return None
        return {
            "event_id": r[0],
            "event_type": r[1],
            "payload_json": self._encryptor.decrypt_text(r[2]),
            "status": r[3],
            "retry_count": r[4],
            "last_error": r[5],
            "created_at": r[6].isoformat() if isinstance(r[6], datetime) else str(r[6]),
            "updated_at": r[7].isoformat() if isinstance(r[7], datetime) else str(r[7]),
        }

    def mark_outbox_delivered(self, event_id: str) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ops.outbox_events SET status = 'DELIVERED', updated_at = now() WHERE event_id = %s",
                    (event_id,),
                )
            conn.commit()

    def mark_outbox_failed(self, event_id: str, error: str, max_attempts: int = 3) -> str:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT retry_count FROM ops.outbox_events WHERE event_id = %s",
                    (event_id,),
                )
                row = cur.fetchone()
                next_count = (int(row[0]) if row else 0) + 1
                new_status = "DLQ" if next_count >= max_attempts else "PENDING"
                cur.execute(
                    """
                    UPDATE ops.outbox_events
                    SET retry_count = %s, status = %s, last_error = %s, updated_at = now()
                    WHERE event_id = %s
                    """,
                    (next_count, new_status, error[:500], event_id),
                )
            conn.commit()
        return new_status

    def save_telemetry_readings(self, project_id: str, readings: list[Any]) -> int:
        rows_to_insert: list[tuple[Any, ...]] = []
        for r in readings or []:
            val = getattr(r, "value", None)
            ts = getattr(r, "timestamp_utc", None)
            if val is None or ts is None:
                continue
            parsed_ts = ts if isinstance(ts, datetime) else parse_iso_timestamp(str(ts))
            if parsed_ts is None:
                continue
            parsed_utc = parsed_ts.astimezone(timezone.utc) if parsed_ts.tzinfo else parsed_ts.replace(tzinfo=timezone.utc)
            if parsed_utc <= EPOCH_SENTINEL_CUTOFF:
                continue
            depth = getattr(r, "depth_level", None)
            rows_to_insert.append(
                (
                    project_id,
                    str(getattr(r, "device_id", "")),
                    str(getattr(r, "external_id", "")),
                    str(getattr(r, "source_code", "weather")),
                    str(getattr(r, "metric", "")),
                    int(depth) if depth is not None else 0,
                    float(val),
                    str(getattr(r, "unit", "") or ""),
                    parsed_utc,
                )
            )
        if not rows_to_insert:
            return 0
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO telemetry.readings (
                        project_id, device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (device_id, metric_key, depth_level, timestamp_utc) DO UPDATE SET
                        value = EXCLUDED.value,
                        iso_unit = EXCLUDED.iso_unit,
                        project_id = EXCLUDED.project_id
                    """,
                    rows_to_insert,
                )
            conn.commit()
        return len(rows_to_insert)

    def query_telemetry_history(
        self,
        project_id: str,
        device_id: str | None = None,
        hours: int = 24,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if device_id:
                    cur.execute(
                        """
                        SELECT device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                        FROM telemetry.readings
                        WHERE project_id = %s AND device_id = %s AND timestamp_utc >= %s
                        ORDER BY timestamp_utc ASC
                        LIMIT %s
                        """,
                        (project_id, device_id, cutoff, limit),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        cur.execute(
                            """
                            SELECT device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                            FROM (
                                SELECT device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                                FROM telemetry.readings
                                WHERE project_id = %s AND device_id = %s
                                ORDER BY timestamp_utc DESC
                                LIMIT %s
                            ) sub
                            ORDER BY timestamp_utc ASC
                            """,
                            (project_id, device_id, limit),
                        )
                        rows = cur.fetchall()
                else:
                    cur.execute(
                        """
                        SELECT device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                        FROM telemetry.readings
                        WHERE project_id = %s AND timestamp_utc >= %s
                        ORDER BY timestamp_utc ASC
                        LIMIT %s
                        """,
                        (project_id, cutoff, limit),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        cur.execute(
                            """
                            SELECT device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                            FROM (
                                SELECT device_id, external_id, source_code, metric_key, depth_level, value, iso_unit, timestamp_utc
                                FROM telemetry.readings
                                WHERE project_id = %s
                                ORDER BY timestamp_utc DESC
                                LIMIT %s
                            ) sub
                            ORDER BY timestamp_utc ASC
                            """,
                            (project_id, limit),
                        )
                        rows = cur.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            ts = r[7]
            ts_str = ts.astimezone(timezone.utc).isoformat() if isinstance(ts, datetime) else str(ts)
            depth_val = int(r[4])
            out.append(
                {
                    "device_id": r[0],
                    "external_id": r[1],
                    "source_code": r[2],
                    "metric": r[3],
                    "value": r[5],
                    "unit": r[6],
                    "depth_level": depth_val if depth_val > 0 else None,
                    "timestamp_utc": ts_str,
                }
            )
        return out
