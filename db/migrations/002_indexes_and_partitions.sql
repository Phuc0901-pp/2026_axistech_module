-- Monthly Range Partitions & Performance Indexes for PostgreSQL 16
CREATE OR REPLACE FUNCTION telemetry.ensure_monthly_partition(p_month date)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    v_start date := date_trunc('month', p_month)::date;
    v_end   date := (date_trunc('month', p_month) + interval '1 month')::date;
    v_name  text := format('readings_%s', to_char(v_start, 'YYYY_MM'));
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS telemetry.%I PARTITION OF telemetry.readings FOR VALUES FROM (%L) TO (%L)',
        v_name,
        v_start::timestamptz,
        v_end::timestamptz
    );
END;
$$;

DO $$
DECLARE
    m date := date '2026-01-01';
BEGIN
    WHILE m <= date '2027-12-01' LOOP
        PERFORM telemetry.ensure_monthly_partition(m);
        m := (m + interval '1 month')::date;
    END LOOP;
END;
$$;

CREATE TABLE IF NOT EXISTS telemetry.readings_default
    PARTITION OF telemetry.readings DEFAULT;

CREATE INDEX IF NOT EXISTS idx_core_devices_project
    ON core.devices (project_id, active);

CREATE INDEX IF NOT EXISTS idx_core_fields_project
    ON core.fields (project_id);

CREATE INDEX IF NOT EXISTS idx_tel_readings_proj_dev_metric_ts
    ON telemetry.readings (project_id, device_id, metric_key, timestamp_utc DESC);

CREATE INDEX IF NOT EXISTS idx_tel_readings_ts_brin
    ON telemetry.readings USING brin (timestamp_utc);

CREATE INDEX IF NOT EXISTS idx_tel_snapshots_project
    ON telemetry.device_snapshots (project_id, status);

CREATE INDEX IF NOT EXISTS idx_ops_outbox_pending
    ON ops.outbox_events (created_at)
    WHERE status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_ops_incidents_project_status
    ON ops.incidents (project_id, status, updated_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_ops_alert_deliveries_project_ts
    ON ops.alert_deliveries (project_id, triggered_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_ts
    ON compliance.audit_log (timestamp_utc DESC);
