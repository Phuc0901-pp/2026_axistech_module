package repository

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/tanbaocorp/axisstream-erp/internal/domain"
)

var epochGuardCutoff = time.Date(1971, 1, 1, 0, 0, 0, 0, time.UTC)

// PostgresMirror persists ERP domain state into the ISO 4-schema PostgreSQL 16 database.
type PostgresMirror struct {
	pool *pgxpool.Pool
}

// NewPostgresMirror opens a bounded pgxpool connection pool and verifies connectivity.
func NewPostgresMirror(ctx context.Context, dsn string) (*PostgresMirror, error) {
	cfg, err := pgxpool.ParseConfig(strings.TrimSpace(dsn))
	if err != nil {
		return nil, fmt.Errorf("parse postgres dsn: %w", err)
	}
	cfg.MaxConns = 12
	cfg.MinConns = 1
	cfg.MaxConnIdleTime = 5 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("connect postgres pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping postgres: %w", err)
	}
	return &PostgresMirror{pool: pool}, nil
}

func (m *PostgresMirror) Close() {
	if m != nil && m.pool != nil {
		m.pool.Close()
	}
}

func (m *PostgresMirror) Healthy(ctx context.Context) bool {
	if m == nil || m.pool == nil {
		return false
	}
	return m.pool.Ping(ctx) == nil
}

func sanitizeTimestampPtr(ts *time.Time) *time.Time {
	if ts == nil || !ts.After(epochGuardCutoff) {
		return nil
	}
	u := ts.UTC()
	return &u
}

func sanitizeWGS84(c *domain.Coordinates) (*float64, *float64) {
	if c == nil {
		return nil, nil
	}
	if c.Latitude < -90 || c.Latitude > 90 || c.Longitude < -180 || c.Longitude > 180 {
		return nil, nil
	}
	lat := c.Latitude
	lon := c.Longitude
	return &lat, &lon
}

// LoadSnapshot hydrates persisted projects, devices, snapshots, forecasts, incidents & audit chain from PostgreSQL.
func (m *PostgresMirror) LoadSnapshot(ctx context.Context) (persistedSnapshot, error) {
	snap := persistedSnapshot{
		Devices:        make(map[string][]domain.Device),
		Snapshots:      make(map[string][]domain.DeviceSnapshot),
		Readings:       make(map[string][]domain.TelemetryReading),
		Fields:         make(map[string][]domain.FieldLocation),
		Assets:         make(map[string][]domain.EquipmentAsset),
		Policies:       make(map[string][]domain.AlertPolicy),
		AlertHistory:   make(map[string][]domain.AlertHistoryItem),
		Providers:      make(map[string][]domain.ProviderConnection),
		ExchangeTokens: make(map[string][]domain.ExchangeTokenInfo),
		WeatherRows:    make(map[string][]domain.WeatherExchangeRow),
		Forecasts:      make(map[string]*domain.ProjectForecastBundle),
		Incidents:      make(map[string]domain.Incident),
		SyncStatus:     domain.SyncStatus{BridgeHealth: "POSTGRES_HYDRATED"},
	}

	projRows, err := m.pool.Query(ctx, `
		SELECT p.id, p.name, COALESCE(o.id, ''), COALESCE(o.name, ''), COALESCE(o.schema_name, 'tbncorp')
		FROM core.projects p
		LEFT JOIN core.organisations o ON o.id = p.organisation_id
		ORDER BY p.name ASC
	`)
	if err != nil {
		return snap, err
	}
	defer projRows.Close()
	for projRows.Next() {
		var p domain.Project
		if err := projRows.Scan(&p.ID, &p.Name, &p.Organisation.ID, &p.Organisation.Name, &p.Organisation.SchemaName); err != nil {
			return snap, err
		}
		snap.Projects = append(snap.Projects, p)
	}

	devRows, err := m.pool.Query(ctx, `
		SELECT id, project_id, external_id, name, source_code, comm_type, active, latitude, longitude, metadata
		FROM core.devices ORDER BY name ASC
	`)
	if err == nil {
		defer devRows.Close()
		for devRows.Next() {
			var d domain.Device
			var projID string
			var lat, lon *float64
			var metaRaw []byte
			if scanErr := devRows.Scan(&d.ID, &projID, &d.ExternalID, &d.Name, &d.SourceCode, &d.CommType, &d.Active, &lat, &lon, &metaRaw); scanErr == nil {
				if lat != nil && lon != nil {
					d.Coordinates = &domain.Coordinates{Latitude: *lat, Longitude: *lon}
				}
				snap.Devices[projID] = append(snap.Devices[projID], d)
			}
		}
	}

	snapRows, err := m.pool.Query(ctx, `
		SELECT project_id, device_id, external_id, source_code, status, latest_timestamp_utc, readings_json, metadata
		FROM telemetry.device_snapshots
	`)
	if err == nil {
		defer snapRows.Close()
		for snapRows.Next() {
			var projID string
			var s domain.DeviceSnapshot
			var readingsRaw, metaRaw []byte
			if scanErr := snapRows.Scan(&projID, &s.DeviceID, &s.ExternalID, &s.SourceCode, &s.Status, &s.LatestTimestampUTC, &readingsRaw, &metaRaw); scanErr == nil {
				_ = json.Unmarshal(readingsRaw, &s.Readings)
				_ = json.Unmarshal(metaRaw, &s.Metadata)
				snap.Snapshots[projID] = append(snap.Snapshots[projID], s)
			}
		}
	}

	fcRows, err := m.pool.Query(ctx, `SELECT project_id, bundle_json FROM telemetry.forecast_bundles`)
	if err == nil {
		defer fcRows.Close()
		for fcRows.Next() {
			var projID string
			var raw []byte
			if scanErr := fcRows.Scan(&projID, &raw); scanErr == nil {
				var bundle domain.ProjectForecastBundle
				if json.Unmarshal(raw, &bundle) == nil {
					snap.Forecasts[projID] = &bundle
				}
			}
		}
	}

	fldRows, err := m.pool.Query(ctx, `SELECT id, project_id, name, category, address, sites_geojson FROM core.fields`)
	if err == nil {
		defer fldRows.Close()
		for fldRows.Next() {
			var f domain.FieldLocation
			var sitesRaw []byte
			if scanErr := fldRows.Scan(&f.ID, &f.ProjectID, &f.Name, &f.Category, &f.Address, &sitesRaw); scanErr == nil {
				_ = json.Unmarshal(sitesRaw, &f.Sites)
				snap.Fields[f.ProjectID] = append(snap.Fields[f.ProjectID], f)
			}
		}
	}

	incRows, err := m.pool.Query(ctx, `
		SELECT id, project_id, policy_name, device_id, device_name, severity, status, message, acknowledged_by, resolved_by, created_at_utc, updated_at_utc
		FROM ops.incidents
	`)
	if err == nil {
		defer incRows.Close()
		for incRows.Next() {
			var inc domain.Incident
			var statusStr string
			if scanErr := incRows.Scan(&inc.ID, &inc.ProjectID, &inc.PolicyName, &inc.DeviceID, &inc.DeviceName, &inc.Severity, &statusStr, &inc.Message, &inc.AcknowledgedBy, &inc.ResolvedBy, &inc.CreatedAtUTC, &inc.UpdatedAtUTC); scanErr == nil {
				inc.Status = domain.IncidentStatus(statusStr)
				snap.Incidents[inc.ID] = inc
			}
		}
	}

	audRows, err := m.pool.Query(ctx, `
		SELECT event_id, timestamp_utc, actor, action, resource_type, resource_id, correlation_id, prev_hash, entry_hash, details
		FROM compliance.audit_log
		ORDER BY seq_id ASC
		LIMIT 1000
	`)
	if err == nil {
		defer audRows.Close()
		for audRows.Next() {
			var e domain.AuditEntry
			if scanErr := audRows.Scan(&e.ID, &e.TimestampUTC, &e.Actor, &e.Action, &e.ResourceType, &e.ResourceID, &e.CorrelationID, &e.PrevHash, &e.EntryHash, &e.Details); scanErr == nil {
				e.PrevHash = strings.TrimSpace(e.PrevHash)
				e.EntryHash = strings.TrimSpace(e.EntryHash)
				snap.AuditLog = append(snap.AuditLog, e)
			}
		}
	}
	return snap, nil
}

// SyncSnapshot writes current ERP entities idempotently into PostgreSQL while keeping audit_log append-only.
func (m *PostgresMirror) SyncSnapshot(ctx context.Context, snap persistedSnapshot) error {
	if m == nil || m.pool == nil {
		return nil
	}
	tx, err := m.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	for _, p := range snap.Projects {
		var orgID any
		if strings.TrimSpace(p.Organisation.ID) != "" {
			if _, err := tx.Exec(ctx, `
				INSERT INTO core.organisations (id, name, schema_name, updated_at)
				VALUES ($1, $2, $3, now())
				ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, schema_name = EXCLUDED.schema_name, updated_at = now()
			`, p.Organisation.ID, p.Organisation.Name, p.Organisation.SchemaName); err != nil {
				return err
			}
			orgID = p.Organisation.ID
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO core.projects (id, organisation_id, name, updated_at)
			VALUES ($1, $2, $3, now())
			ON CONFLICT (id) DO UPDATE SET organisation_id = EXCLUDED.organisation_id, name = EXCLUDED.name, updated_at = now()
		`, p.ID, orgID, p.Name); err != nil {
			return err
		}
	}

	for projID, devs := range snap.Devices {
		for _, d := range devs {
			lat, lon := sanitizeWGS84(d.Coordinates)
			if _, err := tx.Exec(ctx, `
				INSERT INTO core.devices (id, project_id, external_id, name, source_code, comm_type, active, latitude, longitude, updated_at)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
				ON CONFLICT (id) DO UPDATE SET
					project_id = EXCLUDED.project_id, external_id = EXCLUDED.external_id, name = EXCLUDED.name,
					source_code = EXCLUDED.source_code, comm_type = EXCLUDED.comm_type, active = EXCLUDED.active,
					latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, updated_at = now()
			`, d.ID, projID, d.ExternalID, d.Name, d.SourceCode, d.CommType, d.Active, lat, lon); err != nil {
				return err
			}
		}
	}

	for projID, flds := range snap.Fields {
		for _, f := range flds {
			sitesJSON, _ := json.Marshal(f.Sites)
			if _, err := tx.Exec(ctx, `
				INSERT INTO core.fields (id, project_id, name, category, address, sites_geojson, updated_at)
				VALUES ($1, $2, $3, $4, $5, $6, now())
				ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category, address = EXCLUDED.address, sites_geojson = EXCLUDED.sites_geojson, updated_at = now()
			`, f.ID, projID, f.Name, f.Category, f.Address, sitesJSON); err != nil {
				return err
			}
		}
	}

	for projID, assets := range snap.Assets {
		for _, a := range assets {
			lat, lon := sanitizeWGS84(a.Position)
			if _, err := tx.Exec(ctx, `
				INSERT INTO core.assets (id, project_id, name, asset_type, latitude, longitude, updated_at)
				VALUES ($1, $2, $3, $4, $5, $6, now())
				ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, asset_type = EXCLUDED.asset_type, latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, updated_at = now()
			`, a.ID, projID, a.Name, a.AssetType, lat, lon); err != nil {
				return err
			}
		}
	}

	for projID, provs := range snap.Providers {
		for _, pr := range provs {
			pid := pr.ID
			if pid == "" {
				pid = projID + ":" + pr.Code
			}
			if _, err := tx.Exec(ctx, `
				INSERT INTO core.providers (id, project_id, provider_code, name, status, updated_at)
				VALUES ($1, $2, $3, $4, $5, now())
				ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status, updated_at = now()
			`, pid, projID, pr.Code, pr.Name, pr.Status); err != nil {
				return err
			}
		}
	}

	for projID, snaps := range snap.Snapshots {
		for _, s := range snaps {
			rJSON, _ := json.Marshal(s.Readings)
			mJSON, _ := json.Marshal(s.Metadata)
			ts := sanitizeTimestampPtr(s.LatestTimestampUTC)
			pw := "OFF"
			if strings.EqualFold(s.Status, "LIVE") && ts != nil {
				pw = "ON"
			}
			if _, err := tx.Exec(ctx, `
				INSERT INTO telemetry.device_snapshots (device_id, project_id, external_id, source_code, status, power_state, latest_timestamp_utc, readings_json, metadata, updated_at)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
				ON CONFLICT (device_id) DO UPDATE SET
					project_id = EXCLUDED.project_id, external_id = EXCLUDED.external_id, source_code = EXCLUDED.source_code,
					status = EXCLUDED.status, power_state = EXCLUDED.power_state, latest_timestamp_utc = EXCLUDED.latest_timestamp_utc,
					readings_json = EXCLUDED.readings_json, metadata = EXCLUDED.metadata, updated_at = now()
			`, s.DeviceID, projID, s.ExternalID, s.SourceCode, s.Status, pw, ts, rJSON, mJSON); err != nil {
				return err
			}
		}
	}

	for projID, fc := range snap.Forecasts {
		if fc == nil {
			continue
		}
		bJSON, _ := json.Marshal(fc)
		var locName, tz string
		var lat, lon, elev *float64
		if fc.MetNorway.Location != nil {
			locName = fc.MetNorway.Location.Name
			tz = fc.MetNorway.Location.TimeZone
			if fc.MetNorway.Location.Latitude != nil && fc.MetNorway.Location.Longitude != nil {
				lat, lon = sanitizeWGS84(&domain.Coordinates{
					Latitude:  *fc.MetNorway.Location.Latitude,
					Longitude: *fc.MetNorway.Location.Longitude,
				})
			}
			elev = fc.MetNorway.Location.Elevation
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO telemetry.forecast_bundles (project_id, provider_code, status, location_name, latitude, longitude, elevation_m, time_zone, updated_at_utc, bundle_json, updated_at)
			VALUES ($1, 'met_norway', $2, $3, $4, $5, $6, $7, $8, $9, now())
			ON CONFLICT (project_id) DO UPDATE SET
				status = EXCLUDED.status, location_name = EXCLUDED.location_name, latitude = EXCLUDED.latitude,
				longitude = EXCLUDED.longitude, elevation_m = EXCLUDED.elevation_m, time_zone = EXCLUDED.time_zone,
				updated_at_utc = EXCLUDED.updated_at_utc, bundle_json = EXCLUDED.bundle_json, updated_at = now()
		`, projID, fc.MetNorway.Status, locName, lat, lon, elev, tz, sanitizeTimestampPtr(fc.MetNorway.UpdatedAtUTC), bJSON); err != nil {
			return err
		}
	}

	for _, inc := range snap.Incidents {
		if _, err := tx.Exec(ctx, `
			INSERT INTO ops.incidents (id, project_id, policy_name, device_id, device_name, severity, status, message, acknowledged_by, resolved_by, created_at_utc, updated_at_utc)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
			ON CONFLICT (id) DO UPDATE SET
				status = EXCLUDED.status, severity = EXCLUDED.severity, message = EXCLUDED.message,
				acknowledged_by = EXCLUDED.acknowledged_by, resolved_by = EXCLUDED.resolved_by, updated_at_utc = EXCLUDED.updated_at_utc
		`, inc.ID, inc.ProjectID, inc.PolicyName, inc.DeviceID, inc.DeviceName, inc.Severity, string(inc.Status), inc.Message, inc.AcknowledgedBy, inc.ResolvedBy, inc.CreatedAtUTC.UTC(), inc.UpdatedAtUTC.UTC()); err != nil {
			return err
		}
	}

	for _, e := range snap.AuditLog {
		prevH := fmt.Sprintf("%-64s", e.PrevHash)
		entryH := fmt.Sprintf("%-64s", e.EntryHash)
		if _, err := tx.Exec(ctx, `
			INSERT INTO compliance.audit_log (event_id, timestamp_utc, actor, action, resource_type, resource_id, correlation_id, prev_hash, entry_hash, details)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
			ON CONFLICT (event_id) DO NOTHING
		`, e.ID, e.TimestampUTC.UTC(), e.Actor, e.Action, e.ResourceType, e.ResourceID, e.CorrelationID, prevH[:64], entryH[:64], e.Details); err != nil {
			return err
		}
	}

	return tx.Commit(ctx)
}
