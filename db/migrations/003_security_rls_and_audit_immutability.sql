-- ISO/IEC 27001 Controls: Immutable Audit Trigger, Tenant Row-Level Security & Least-Privilege Roles
CREATE OR REPLACE FUNCTION compliance.prevent_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'ISO 27001 VIOLATION: compliance.audit_log is append-only (% forbidden)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_compliance_audit_immutable ON compliance.audit_log;
CREATE TRIGGER trg_compliance_audit_immutable
    BEFORE UPDATE OR DELETE ON compliance.audit_log
    FOR EACH ROW
    EXECUTE FUNCTION compliance.prevent_audit_mutation();

-- Tenant Row-Level Security (system sync runs with empty app.current_project_id; scoped requests filter by project_id)
ALTER TABLE core.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry.readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry.device_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.alert_deliveries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_tenant_devices ON core.devices;
CREATE POLICY p_tenant_devices ON core.devices
    USING (
        coalesce(current_setting('app.current_project_id', true), '') = ''
        OR project_id = current_setting('app.current_project_id', true)
    );

DROP POLICY IF EXISTS p_tenant_readings ON telemetry.readings;
CREATE POLICY p_tenant_readings ON telemetry.readings
    USING (
        coalesce(current_setting('app.current_project_id', true), '') = ''
        OR project_id = current_setting('app.current_project_id', true)
    );

DROP POLICY IF EXISTS p_tenant_snapshots ON telemetry.device_snapshots;
CREATE POLICY p_tenant_snapshots ON telemetry.device_snapshots
    USING (
        coalesce(current_setting('app.current_project_id', true), '') = ''
        OR project_id = current_setting('app.current_project_id', true)
    );

DROP POLICY IF EXISTS p_tenant_incidents ON ops.incidents;
CREATE POLICY p_tenant_incidents ON ops.incidents
    USING (
        coalesce(current_setting('app.current_project_id', true), '') = ''
        OR project_id = current_setting('app.current_project_id', true)
    );

DROP POLICY IF EXISTS p_tenant_alert_deliveries ON ops.alert_deliveries;
CREATE POLICY p_tenant_alert_deliveries ON ops.alert_deliveries
    USING (
        coalesce(current_setting('app.current_project_id', true), '') = ''
        OR project_id = current_setting('app.current_project_id', true)
    );

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agtech_bridge_rw') THEN
        CREATE ROLE agtech_bridge_rw NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agtech_erp_app') THEN
        CREATE ROLE agtech_erp_app NOLOGIN;
    END IF;
END;
$$;

GRANT USAGE ON SCHEMA core, telemetry, ops TO agtech_bridge_rw;
GRANT USAGE ON SCHEMA core, telemetry, ops, compliance TO agtech_erp_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA core, telemetry, ops TO agtech_bridge_rw, agtech_erp_app;
GRANT SELECT, INSERT ON compliance.audit_log TO agtech_erp_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA compliance TO agtech_erp_app;
REVOKE UPDATE, DELETE, TRUNCATE ON compliance.audit_log FROM PUBLIC, agtech_bridge_rw, agtech_erp_app;
