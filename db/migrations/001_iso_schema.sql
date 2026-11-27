-- ISO/IEC 42010, ISO/IEC 27001, ISO 8601, ISO 80000 & ISO 19115 PostgreSQL Schema
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS telemetry;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS compliance;

CREATE TABLE IF NOT EXISTS core.organisations (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    schema_name text NOT NULL DEFAULT 'tbncorp',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.projects (
    id              text PRIMARY KEY,
    organisation_id text REFERENCES core.organisations(id) ON DELETE SET NULL,
    name            text NOT NULL,
    time_zone       text NOT NULL DEFAULT 'UTC',
    latitude        double precision CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
    longitude       double precision CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180)),
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.devices (
    id              text PRIMARY KEY,
    project_id      text NOT NULL REFERENCES core.projects(id) ON DELETE CASCADE,
    external_id     text NOT NULL DEFAULT '',
    name            text NOT NULL,
    source_code     text NOT NULL DEFAULT 'weather',
    comm_type       text NOT NULL DEFAULT '',
    active          boolean NOT NULL DEFAULT true,
    latitude        double precision CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
    longitude       double precision CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180)),
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.fields (
    id            text PRIMARY KEY,
    project_id    text NOT NULL REFERENCES core.projects(id) ON DELETE CASCADE,
    name          text NOT NULL,
    category      text NOT NULL DEFAULT 'field',
    address       text NOT NULL DEFAULT '',
    sites_geojson jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.assets (
    id          text PRIMARY KEY,
    project_id  text NOT NULL REFERENCES core.projects(id) ON DELETE CASCADE,
    name        text NOT NULL,
    asset_type  text NOT NULL DEFAULT '',
    latitude    double precision CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
    longitude   double precision CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180)),
    metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.providers (
    id            text PRIMARY KEY,
    project_id    text NOT NULL REFERENCES core.projects(id) ON DELETE CASCADE,
    provider_code text NOT NULL,
    name          text NOT NULL DEFAULT '',
    status        text NOT NULL DEFAULT 'CONNECTED',
    metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry.metric_catalog (
    metric_key  text PRIMARY KEY,
    vi_label    text NOT NULL,
    vi_tooltip  text NOT NULL,
    iso_unit    text NOT NULL DEFAULT '',
    category    text NOT NULL DEFAULT 'other',
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Time-series partitioned table (ISO 8601 UTC + Epoch-1970 sentinel guard)
CREATE TABLE IF NOT EXISTS telemetry.readings (
    project_id    text NOT NULL,
    device_id     text NOT NULL,
    external_id   text NOT NULL DEFAULT '',
    source_code   text NOT NULL DEFAULT 'weather',
    metric_key    text NOT NULL,
    depth_level   integer NOT NULL DEFAULT 0 CHECK (depth_level >= 0),
    value         double precision NOT NULL,
    iso_unit      text NOT NULL DEFAULT '',
    timestamp_utc timestamptz NOT NULL CHECK (timestamp_utc > '1971-01-01T00:00:00Z'::timestamptz),
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (device_id, metric_key, depth_level, timestamp_utc)
) PARTITION BY RANGE (timestamp_utc);

CREATE TABLE IF NOT EXISTS telemetry.device_snapshots (
    device_id            text PRIMARY KEY,
    project_id           text NOT NULL,
    external_id          text NOT NULL DEFAULT '',
    source_code          text NOT NULL DEFAULT 'weather',
    status               text NOT NULL DEFAULT 'UNKNOWN',
    power_state          text NOT NULL DEFAULT 'OFF',
    latest_timestamp_utc timestamptz CHECK (latest_timestamp_utc IS NULL OR latest_timestamp_utc > '1971-01-01T00:00:00Z'::timestamptz),
    readings_json        jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata             jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry.forecast_bundles (
    project_id     text PRIMARY KEY,
    provider_code  text NOT NULL DEFAULT 'met_norway',
    status         text NOT NULL DEFAULT 'DISCONNECTED',
    location_name  text NOT NULL DEFAULT '',
    latitude       double precision CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
    longitude      double precision CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180)),
    elevation_m    double precision,
    time_zone      text NOT NULL DEFAULT 'UTC',
    updated_at_utc timestamptz,
    bundle_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.alert_policies (
    id          text PRIMARY KEY,
    project_id  text NOT NULL,
    name        text NOT NULL,
    priority    text NOT NULL DEFAULT 'MEDIUM',
    status      text NOT NULL DEFAULT 'ACTIVE',
    rule_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.alert_deliveries (
    id                 text PRIMARY KEY,
    project_id         text NOT NULL,
    policy_name        text NOT NULL DEFAULT '',
    device_name        text NOT NULL DEFAULT '',
    rule_description   text NOT NULL DEFAULT '',
    delivery_status    text NOT NULL DEFAULT 'DELIVERED',
    notification_count integer NOT NULL DEFAULT 1,
    triggered_at_utc   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.incidents (
    id              text PRIMARY KEY,
    project_id      text NOT NULL,
    policy_name     text NOT NULL DEFAULT '',
    device_id       text NOT NULL DEFAULT '',
    device_name     text NOT NULL DEFAULT '',
    severity        text NOT NULL DEFAULT 'MEDIUM',
    status          text NOT NULL CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
    message         text NOT NULL DEFAULT '',
    acknowledged_by text NOT NULL DEFAULT '',
    resolved_by     text NOT NULL DEFAULT '',
    created_at_utc  timestamptz NOT NULL DEFAULT now(),
    updated_at_utc  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.sync_cursors (
    scope_key   text PRIMARY KEY,
    cursor_utc  timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.dedup_keys (
    dedup_hash text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.outbox_events (
    event_id          text PRIMARY KEY,
    event_type        text NOT NULL,
    payload_encrypted text NOT NULL,
    status            text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DELIVERED', 'DLQ')),
    retry_count       integer NOT NULL DEFAULT 0,
    last_error        text NOT NULL DEFAULT '',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- ISO 27001 Immutable Hash-Chained Audit Trail
CREATE TABLE IF NOT EXISTS compliance.audit_log (
    seq_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id       text NOT NULL UNIQUE,
    timestamp_utc  timestamptz NOT NULL DEFAULT now(),
    actor          text NOT NULL,
    action         text NOT NULL,
    resource_type  text NOT NULL,
    resource_id    text NOT NULL,
    correlation_id text NOT NULL DEFAULT '',
    prev_hash      char(64) NOT NULL,
    entry_hash     char(64) NOT NULL,
    details        text NOT NULL DEFAULT ''
);
