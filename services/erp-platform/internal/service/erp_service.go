package service

import (
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/bridgeclient"
	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/realtime"
	"github.com/tanbaocorp/axisstream-erp/internal/repository"
)

// BridgeClient defines the upstream bridge operations needed by ERPService.
type BridgeClient interface {
	FetchProjects(ctx context.Context, cid string) ([]domain.Project, error)
	FetchDevices(ctx context.Context, projectID, cid string) ([]domain.Device, error)
	FetchTelemetry(ctx context.Context, projectID, cid string) ([]domain.DeviceSnapshot, error)
	FetchTelemetryHistory(ctx context.Context, projectID, deviceID string, hours int, cid string) ([]domain.TelemetryReading, error)
	FetchFields(ctx context.Context, projectID, cid string) ([]domain.FieldLocation, error)
	FetchAssets(ctx context.Context, projectID, cid string) ([]domain.EquipmentAsset, error)
	FetchAlertPolicies(ctx context.Context, projectID, cid string) ([]domain.AlertPolicy, error)
	FetchAlertHistory(ctx context.Context, projectID, cid string) ([]domain.AlertHistoryItem, error)
	FetchProviders(ctx context.Context, projectID, cid string) ([]domain.ProviderConnection, error)
	FetchWeatherExchange(ctx context.Context, projectID, cid string) ([]domain.ExchangeTokenInfo, []domain.WeatherExchangeRow, error)
	FetchWeatherForecast(ctx context.Context, projectID, cid string) (*domain.ProjectForecastBundle, error)
	TriggerSync(ctx context.Context, cid string) error
	FetchHealthStatus(ctx context.Context) (string, string, string, error)
	CheckHealth(ctx context.Context) (string, error)
	SubscribeStream(ctx context.Context, onEvent func(bridgeclient.BridgeSSEEvent)) error
}

type ERPService struct {
	store         *repository.Store
	bridge        BridgeClient
	hub           *realtime.Hub
	log           *slog.Logger
	rateLimitRPM  int
	requireAPIKey bool
}

func NewERPService(store *repository.Store, bridge BridgeClient, hub *realtime.Hub, log *slog.Logger) *ERPService {
	return &ERPService{store: store, bridge: bridge, hub: hub, log: log, rateLimitRPM: 300}
}

func (s *ERPService) ConfigureSecurityPolicy(rateLimitRPM int, requireAPIKey bool) {
	if rateLimitRPM > 0 {
		s.rateLimitRPM = rateLimitRPM
	}
	s.requireAPIKey = requireAPIKey
}

func (s *ERPService) SyncOnce(ctx context.Context, cid string) error {
	projects, err := s.bridge.FetchProjects(ctx, cid)
	if err != nil {
		st := s.store.GetSyncStatus()
		st.BridgeHealth = "DEGRADED"
		st.LastError = err.Error()
		s.store.SetSyncStatus(st)
		return err
	}
	s.store.SaveProjects(projects)

	totalNew := 0
	var lastPartialErr string
	for _, p := range projects {
		devices, err := s.bridge.FetchDevices(ctx, p.ID, cid)
		if err != nil {
			lastPartialErr = err.Error()
			s.log.Warn("Partial sync failure fetching devices", "project_id", p.ID, "error", err.Error())
			continue
		}
		snaps, _ := s.bridge.FetchTelemetry(ctx, p.ID, cid)
		fields, _ := s.bridge.FetchFields(ctx, p.ID, cid)
		assets, _ := s.bridge.FetchAssets(ctx, p.ID, cid)
		policies, _ := s.bridge.FetchAlertPolicies(ctx, p.ID, cid)
		history, _ := s.bridge.FetchAlertHistory(ctx, p.ID, cid)
		providers, _ := s.bridge.FetchProviders(ctx, p.ID, cid)
		tokens, weatherRows, _ := s.bridge.FetchWeatherExchange(ctx, p.ID, cid)
		forecastBundle, _ := s.bridge.FetchWeatherForecast(ctx, p.ID, cid)

		totalNew += s.store.SaveProjectData(
			p.ID, devices, snaps, fields, assets, policies, history, providers, tokens, weatherRows,
		)
		if forecastBundle != nil {
			s.store.SaveForecast(p.ID, forecastBundle)
		}
	}

	now := time.Now().UTC()
	st := s.store.GetSyncStatus()
	st.LastSyncUTC = &now
	st.SyncCount++
	st.BridgeHealth = "READY"
	st.LastError = lastPartialErr
	if len(projects) == 0 {
		if healthStatus, _, bridgeErr, _ := s.bridge.FetchHealthStatus(ctx); bridgeErr != "" || healthStatus != "READY" {
			st.BridgeHealth = healthStatus
			if bridgeErr != "" {
				st.LastError = "Bridge sync error: " + bridgeErr
			} else {
				st.LastError = "Bridge returned 0 projects (verify AXISSTREAM_MODE=live and credentials)"
			}
		} else {
			st.LastError = "Bridge returned 0 projects (check AXISSTREAM_MODE and credentials on Python Bridge)"
		}
	}
	s.store.SetSyncStatus(st)

	s.store.AppendAudit(domain.AuditEntry{
		ID:            fmt.Sprintf("aud-%d", now.UnixNano()),
		TimestampUTC:  now,
		Actor:         "system:sync-worker",
		Action:        "SYNC_CYCLE_COMPLETED",
		ResourceType:  "axisstream_bridge",
		ResourceID:    "all_projects",
		CorrelationID: cid,
		Details:       fmt.Sprintf("projects=%d new_readings=%d", len(projects), totalNew),
	})

	s.hub.Broadcast(realtime.Event{
		Type:         "sync_update",
		TimestampUTC: now,
		Payload: map[string]any{
			"sync_count":   st.SyncCount,
			"projects":     len(projects),
			"new_readings": totalNew,
		},
	})
	return nil
}

// ForceSyncNow triggers an immediate upstream fetch on the Python Bridge before syncing the ERP store.
func (s *ERPService) ForceSyncNow(ctx context.Context, cid string) error {
	trigErr := s.bridge.TriggerSync(ctx, cid)
	syncErr := s.SyncOnce(ctx, cid)
	if trigErr != nil {
		st := s.store.GetSyncStatus()
		st.BridgeHealth = "DEGRADED"
		st.LastError = "Bridge trigger failed: " + trigErr.Error()
		s.store.SetSyncStatus(st)
		return trigErr
	}
	return syncErr
}

func (s *ERPService) GetDashboard(projectID string) domain.DashboardSummary {
	projects := s.store.GetProjects()
	activeID := projectID
	if activeID == "" && len(projects) > 0 {
		// Smart default: pick first AxisTech project containing active devices
		for _, p := range projects {
			if len(s.store.GetDevices(p.ID)) > 0 {
				activeID = p.ID
				break
			}
		}
		if activeID == "" {
			activeID = projects[0].ID
		}
	}
	devices := s.store.GetDevices(activeID)
	snaps := s.store.GetSnapshots(activeID)
	fields := s.store.GetFields(activeID)
	assets := s.store.GetAssets(activeID)
	policies := s.store.GetPolicies(activeID)
	providers := s.store.GetProviders(activeID)
	_, weatherRows := s.store.GetWeatherExchange(activeID)
	incidents := s.store.ListIncidents(activeID, "")

	live, noData, offline := 0, 0, 0
	latestWeather := make(map[string]float64)
	for _, snap := range snaps {
		switch snap.Status {
		case "LIVE":
			live++
		case "NO_DATA":
			noData++
		default:
			offline++
		}
		if snap.SourceCode == "weather" {
			for _, r := range snap.Readings {
				if r.Value != nil {
					latestWeather[r.Metric] = *r.Value
				}
			}
		}
	}

	openInc, ackInc := 0, 0
	for _, inc := range incidents {
		switch inc.Status {
		case domain.IncidentOpen:
			openInc++
		case domain.IncidentAcknowledged:
			ackInc++
		}
	}
	activePol := 0
	for _, pol := range policies {
		if pol.Status == "ACTIVE" {
			activePol++
		}
	}

	posture := s.GetSecurityPosture()
	cryptoStatus := "Standby (Set ERP_ENCRYPTION_KEY)"
	if posture.EncryptionAtRest {
		cryptoStatus = "AES-256-GCM Active"
	}
	chainStatus := "VERIFIED"
	if !posture.AuditChainVerified {
		chainStatus = "TAMPER_ALERT"
	}

	return domain.DashboardSummary{
		ActiveProjectID: activeID,
		Projects:        projects,
		TotalDevices:    len(devices),
		LiveDevices:     live,
		NoDataDevices:   noData,
		OfflineDevices:  offline,
		TotalFields:     len(fields),
		TotalAssets:     len(assets),
		OpenIncidents:   openInc,
		AckIncidents:    ackInc,
		ActivePolicies:  activePol,
		ExchangeRows:    len(weatherRows),
		LatestWeather:   latestWeather,
		Snapshots:       snaps,
		Devices:         devices,
		SyncStatus:      s.store.GetSyncStatus(),
		Providers:       providers,
		Forecast:        s.store.GetForecast(activeID),
		Security:        posture,
		ISOCompliance: map[string]string{
			"ISO_42010":        "Hexagonal ACL Verified",
			"ISO_27001":        "Zero-Secret & Redacted Audit",
			"ISO_27001_CRYPTO": cryptoStatus,
			"AUDIT_CHAIN":      chainStatus,
			"ISO_25010":        "Circuit Breaker + Outbox",
			"ISO_8601":         "UTC Canonical Timestamps",
		},
	}
}

func (s *ERPService) GetSecurityPosture() domain.SecurityPosture {
	encEnabled := s.store.EncryptionEnabled()
	algo := "NONE (Set ERP_ENCRYPTION_KEY)"
	if encEnabled {
		algo = "AES-256-GCM"
	}
	return domain.SecurityPosture{
		EncryptionAtRest:    encEnabled,
		EncryptionAlgorithm: algo,
		AuditChainVerified:  s.store.VerifyAuditChain(),
		AuditEntries:        s.store.AuditCount(),
		RateLimitRPM:        s.rateLimitRPM,
		APIKeyGuardEnabled:  s.requireAPIKey,
		ReadOnlyCloudSync:   true,
		CSPPolicy:           "script-src 'self' + HTTPS tile allowlist",
	}
}

func (s *ERPService) GetTelemetryHistory(ctx context.Context, projectID, deviceID string, hours int, cid string) []domain.TelemetryReading {
	if hours <= 0 {
		hours = 24
	}
	if s.bridge != nil {
		if hist, err := s.bridge.FetchTelemetryHistory(ctx, projectID, deviceID, hours, cid); err == nil && len(hist) > 0 {
			return hist
		}
	}
	return s.store.GetReadings(projectID, deviceID)
}

func (s *ERPService) AcknowledgeIncident(id, actor, notes, cid string) (domain.Incident, error) {
	inc, ok := s.store.GetIncident(id)
	if !ok {
		return domain.Incident{}, domain.ErrNotFound
	}
	if inc.Status != domain.IncidentOpen {
		return domain.Incident{}, fmt.Errorf("%w: cannot acknowledge incident in status %s", domain.ErrInvalidTransition, inc.Status)
	}
	if strings.TrimSpace(actor) == "" {
		actor = "erp-operator"
	}
	now := time.Now().UTC()
	inc.Status = domain.IncidentAcknowledged
	inc.AcknowledgedBy = actor
	inc.Notes = notes
	inc.UpdatedAtUTC = now
	if err := s.store.UpdateIncident(inc); err != nil {
		return domain.Incident{}, err
	}
	s.store.AppendAudit(domain.AuditEntry{
		ID:            fmt.Sprintf("aud-%d", now.UnixNano()),
		TimestampUTC:  now,
		Actor:         actor,
		Action:        "INCIDENT_ACKNOWLEDGED",
		ResourceType:  "incident",
		ResourceID:    inc.ID,
		CorrelationID: cid,
		Details:       notes,
	})
	s.hub.Broadcast(realtime.Event{Type: "incident_update", TimestampUTC: now, Payload: inc})
	return inc, nil
}

func (s *ERPService) ResolveIncident(id, actor, notes, cid string) (domain.Incident, error) {
	inc, ok := s.store.GetIncident(id)
	if !ok {
		return domain.Incident{}, domain.ErrNotFound
	}
	if inc.Status == domain.IncidentResolved {
		return domain.Incident{}, fmt.Errorf("%w: incident already resolved", domain.ErrInvalidTransition)
	}
	if strings.TrimSpace(actor) == "" {
		actor = "erp-operator"
	}
	now := time.Now().UTC()
	inc.Status = domain.IncidentResolved
	inc.ResolvedBy = actor
	if notes != "" {
		inc.Notes = notes
	}
	inc.UpdatedAtUTC = now
	if err := s.store.UpdateIncident(inc); err != nil {
		return domain.Incident{}, err
	}
	s.store.AppendAudit(domain.AuditEntry{
		ID:            fmt.Sprintf("aud-%d", now.UnixNano()),
		TimestampUTC:  now,
		Actor:         actor,
		Action:        "INCIDENT_RESOLVED",
		ResourceType:  "incident",
		ResourceID:    inc.ID,
		CorrelationID: cid,
		Details:       notes,
	})
	s.hub.Broadcast(realtime.Event{Type: "incident_update", TimestampUTC: now, Payload: inc})
	return inc, nil
}

func fmtOptFloat(v *float64) string {
	if v == nil {
		return ""
	}
	return strconv.FormatFloat(*v, 'f', 2, 64)
}

// ExportWeatherCSV exports all 17 columns of tbncorp.weather in RFC 4180 CSV format.
func (s *ERPService) ExportWeatherCSV(projectID string) ([]byte, error) {
	_, rows := s.store.GetWeatherExchange(projectID)
	var buf bytes.Buffer
	w := csv.NewWriter(&buf)
	header := []string{
		"code", "time", "temperature_avg", "humidity_avg", "deltat_avg", "dewpoint_avg",
		"atmos_pressure_avg", "msl_pressure", "rainfall", "rainfall_total",
		"wind_speed_avg", "wind_speed_min", "wind_speed_max", "wind_dir_deg_avg",
		"wind_dir_var_avg", "solar_rad_avg", "uv_index_avg",
	}
	if err := w.Write(header); err != nil {
		return nil, err
	}
	for _, r := range rows {
		rec := []string{
			r.Code,
			r.Time.UTC().Format(time.RFC3339),
			fmtOptFloat(r.TemperatureAvg),
			fmtOptFloat(r.HumidityAvg),
			fmtOptFloat(r.DeltaTAvg),
			fmtOptFloat(r.DewpointAvg),
			fmtOptFloat(r.AtmosPressureAvg),
			fmtOptFloat(r.MSLPressure),
			fmtOptFloat(r.Rainfall),
			fmtOptFloat(r.RainfallTotal),
			fmtOptFloat(r.WindSpeedAvg),
			fmtOptFloat(r.WindSpeedMin),
			fmtOptFloat(r.WindSpeedMax),
			fmtOptFloat(r.WindDirDegAvg),
			fmtOptFloat(r.WindDirVarAvg),
			fmtOptFloat(r.SolarRadAvg),
			fmtOptFloat(r.UVIndexAvg),
		}
		if err := w.Write(rec); err != nil {
			return nil, err
		}
	}
	w.Flush()
	return buf.Bytes(), w.Error()
}
