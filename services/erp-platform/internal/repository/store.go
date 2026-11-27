package repository

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/security"
)

type persistedSnapshot struct {
	Projects       []domain.Project                      `json:"projects"`
	Devices        map[string][]domain.Device            `json:"devices"`
	Snapshots      map[string][]domain.DeviceSnapshot    `json:"snapshots"`
	Readings       map[string][]domain.TelemetryReading  `json:"readings"`
	Fields         map[string][]domain.FieldLocation     `json:"fields"`
	Assets         map[string][]domain.EquipmentAsset    `json:"assets"`
	Policies       map[string][]domain.AlertPolicy       `json:"policies"`
	AlertHistory   map[string][]domain.AlertHistoryItem  `json:"alert_history"`
	Providers      map[string][]domain.ProviderConnection  `json:"providers"`
	ExchangeTokens map[string][]domain.ExchangeTokenInfo   `json:"exchange_tokens"`
	WeatherRows    map[string][]domain.WeatherExchangeRow  `json:"weather_rows"`
	Forecasts      map[string]*domain.ProjectForecastBundle `json:"forecasts"`
	Incidents      map[string]domain.Incident              `json:"incidents"`
	AuditLog       []domain.AuditEntry                   `json:"audit_log"`
	SyncStatus     domain.SyncStatus                     `json:"sync_status"`
}

// Store is a thread-safe in-memory ERP state store with optional atomic JSON persistence.
type Store struct {
	mu             sync.RWMutex
	filePath       string
	pgMirror       *PostgresMirror
	cipher         *security.AESCipher
	projects       []domain.Project
	devices        map[string][]domain.Device
	snapshots      map[string][]domain.DeviceSnapshot
	readings       map[string][]domain.TelemetryReading
	dedup          map[string]struct{}
	fields         map[string][]domain.FieldLocation
	assets         map[string][]domain.EquipmentAsset
	policies       map[string][]domain.AlertPolicy
	alertHistory   map[string][]domain.AlertHistoryItem
	providers      map[string][]domain.ProviderConnection
	exchangeTokens map[string][]domain.ExchangeTokenInfo
	weatherRows    map[string][]domain.WeatherExchangeRow
	forecasts      map[string]*domain.ProjectForecastBundle
	incidents      map[string]domain.Incident
	auditLog       []domain.AuditEntry
	syncStatus     domain.SyncStatus
}

func NewStore(filePath string) (*Store, error) {
	return NewEncryptedStore(filePath, "")
}

func NewEncryptedStore(filePath, encryptionKey string) (*Store, error) {
	var aesCipher *security.AESCipher
	if encryptionKey != "" {
		c, err := security.NewAESCipher(encryptionKey)
		if err != nil {
			return nil, err
		}
		aesCipher = c
	}
	s := &Store{
		filePath:       filePath,
		cipher:         aesCipher,
		devices:        make(map[string][]domain.Device),
		snapshots:      make(map[string][]domain.DeviceSnapshot),
		readings:       make(map[string][]domain.TelemetryReading),
		dedup:          make(map[string]struct{}),
		fields:         make(map[string][]domain.FieldLocation),
		assets:         make(map[string][]domain.EquipmentAsset),
		policies:       make(map[string][]domain.AlertPolicy),
		alertHistory:   make(map[string][]domain.AlertHistoryItem),
		providers:      make(map[string][]domain.ProviderConnection),
		exchangeTokens: make(map[string][]domain.ExchangeTokenInfo),
		weatherRows:    make(map[string][]domain.WeatherExchangeRow),
		forecasts:      make(map[string]*domain.ProjectForecastBundle),
		incidents:      make(map[string]domain.Incident),
		syncStatus:     domain.SyncStatus{BridgeHealth: "UNKNOWN"},
	}
	if filePath != "" {
		if err := s.load(); err != nil {
			return nil, err
		}
	}
	return s, nil
}

func dedupKey(r domain.TelemetryReading) string {
	depth := 0
	if r.DepthLevel != nil {
		depth = *r.DepthLevel
	}
	return fmt.Sprintf("%s|%s|%d|%s", r.DeviceID, r.Metric, depth, r.TimestampUTC.UTC().Format(time.RFC3339Nano))
}

func (s *Store) load() error {
	raw, err := os.ReadFile(s.filePath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	if len(raw) == 0 {
		return nil
	}
	payload, _, err := s.cipher.DecryptEnvelope(raw)
	if err != nil {
		return err
	}
	var snap persistedSnapshot
	if err := json.Unmarshal(payload, &snap); err != nil {
		return err
	}
	s.applySnapshotLocked(snap)
	return nil
}

func (s *Store) applySnapshotLocked(snap persistedSnapshot) {
	s.projects = snap.Projects
	if snap.Devices != nil {
		s.devices = snap.Devices
	}
	if snap.Snapshots != nil {
		s.snapshots = snap.Snapshots
	}
	if snap.Readings != nil {
		s.readings = snap.Readings
		for _, list := range s.readings {
			for _, r := range list {
				s.dedup[dedupKey(r)] = struct{}{}
			}
		}
	}
	if snap.Fields != nil {
		s.fields = snap.Fields
	}
	if snap.Assets != nil {
		s.assets = snap.Assets
	}
	if snap.Policies != nil {
		s.policies = snap.Policies
	}
	if snap.AlertHistory != nil {
		s.alertHistory = snap.AlertHistory
	}
	if snap.Providers != nil {
		s.providers = snap.Providers
	}
	if snap.ExchangeTokens != nil {
		s.exchangeTokens = snap.ExchangeTokens
	}
	if snap.WeatherRows != nil {
		s.weatherRows = snap.WeatherRows
	}
	if snap.Forecasts != nil {
		s.forecasts = snap.Forecasts
	}
	if snap.Incidents != nil {
		s.incidents = snap.Incidents
	}
	s.auditLog = snap.AuditLog
	s.syncStatus = snap.SyncStatus
}

// AttachPostgres binds a PostgreSQL 16 mirror and hydrates empty in-memory state from Postgres if available.
func (s *Store) AttachPostgres(ctx context.Context, mirror *PostgresMirror) error {
	if mirror == nil {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.pgMirror = mirror
	if len(s.projects) == 0 && len(s.auditLog) == 0 {
		loaded, err := mirror.LoadSnapshot(ctx)
		if err == nil && (len(loaded.Projects) > 0 || len(loaded.AuditLog) > 0) {
			s.applySnapshotLocked(loaded)
			return nil
		}
	}
	return mirror.SyncSnapshot(ctx, s.snapshotLocked())
}

func (s *Store) snapshotLocked() persistedSnapshot {
	return persistedSnapshot{
		Projects:       s.projects,
		Devices:        s.devices,
		Snapshots:      s.snapshots,
		Readings:       s.readings,
		Fields:         s.fields,
		Assets:         s.assets,
		Policies:       s.policies,
		AlertHistory:   s.alertHistory,
		Providers:      s.providers,
		ExchangeTokens: s.exchangeTokens,
		WeatherRows:    s.weatherRows,
		Forecasts:      s.forecasts,
		Incidents:      s.incidents,
		AuditLog:       s.auditLog,
		SyncStatus:     s.syncStatus,
	}
}

func (s *Store) persistLocked() error {
	snap := s.snapshotLocked()
	if s.pgMirror != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		_ = s.pgMirror.SyncSnapshot(ctx, snap)
		cancel()
	}
	if s.filePath == "" {
		return nil
	}
	data, err := json.MarshalIndent(snap, "", "  ")
	if err != nil {
		return err
	}
	if s.cipher != nil {
		data, err = s.cipher.EncryptEnvelope(data)
		if err != nil {
			return err
		}
	}
	dir := filepath.Dir(s.filePath)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	tmp := s.filePath + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, s.filePath)
}

func (s *Store) SaveProjects(projects []domain.Project) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.projects = append([]domain.Project(nil), projects...)
	_ = s.persistLocked()
}

func (s *Store) GetProjects() []domain.Project {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.Project(nil), s.projects...)
}

func (s *Store) SaveProjectData(
	projectID string,
	devices []domain.Device,
	snapshots []domain.DeviceSnapshot,
	fields []domain.FieldLocation,
	assets []domain.EquipmentAsset,
	policies []domain.AlertPolicy,
	history []domain.AlertHistoryItem,
	providers []domain.ProviderConnection,
	tokens []domain.ExchangeTokenInfo,
	weatherRows []domain.WeatherExchangeRow,
) int {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.devices[projectID] = append([]domain.Device(nil), devices...)
	s.snapshots[projectID] = append([]domain.DeviceSnapshot(nil), snapshots...)
	s.fields[projectID] = append([]domain.FieldLocation(nil), fields...)
	s.assets[projectID] = append([]domain.EquipmentAsset(nil), assets...)
	s.policies[projectID] = append([]domain.AlertPolicy(nil), policies...)
	s.alertHistory[projectID] = append([]domain.AlertHistoryItem(nil), history...)
	s.providers[projectID] = append([]domain.ProviderConnection(nil), providers...)
	s.exchangeTokens[projectID] = append([]domain.ExchangeTokenInfo(nil), tokens...)
	s.weatherRows[projectID] = append([]domain.WeatherExchangeRow(nil), weatherRows...)

	addedReadings := 0
	for _, snap := range snapshots {
		for _, r := range snap.Readings {
			k := dedupKey(r)
			if _, exists := s.dedup[k]; !exists {
				s.dedup[k] = struct{}{}
				s.readings[projectID] = append(s.readings[projectID], r)
				addedReadings++
			}
		}
	}
	// Keep bounded reading history per project (max 2000 latest)
	if len(s.readings[projectID]) > 2000 {
		s.readings[projectID] = s.readings[projectID][len(s.readings[projectID])-2000:]
	}

	now := time.Now().UTC()
	for _, pol := range policies {
		if pol.Status == "ACTIVE" {
			incID := "inc-" + pol.ID
			if existing, ok := s.incidents[incID]; ok {
				// Preserve operator workflow state (ACKNOWLEDGED or RESOLVED)
				existing.PolicyName = pol.Name
				existing.Severity = pol.Priority
				existing.Message = pol.MessageTemplate
				s.incidents[incID] = existing
			} else {
				s.incidents[incID] = domain.Incident{
					ID:           incID,
					ProjectID:    projectID,
					PolicyName:   pol.Name,
					DeviceID:     pol.EntityID,
					DeviceName:   pol.DeviceName,
					Severity:     pol.Priority,
					Status:       domain.IncidentOpen,
					Message:      pol.MessageTemplate,
					CreatedAtUTC: now,
					UpdatedAtUTC: now,
				}
			}
		}
	}
	_ = s.persistLocked()
	return addedReadings
}

func (s *Store) GetDevices(projectID string) []domain.Device {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.Device(nil), s.devices[projectID]...)
}

func (s *Store) GetSnapshots(projectID string) []domain.DeviceSnapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.DeviceSnapshot(nil), s.snapshots[projectID]...)
}

func (s *Store) GetReadings(projectID, deviceID string) []domain.TelemetryReading {
	s.mu.RLock()
	defer s.mu.RUnlock()
	all := s.readings[projectID]
	if deviceID == "" {
		return append([]domain.TelemetryReading(nil), all...)
	}
	var out []domain.TelemetryReading
	for _, r := range all {
		if r.DeviceID == deviceID || r.ExternalID == deviceID {
			out = append(out, r)
		}
	}
	return out
}

func (s *Store) GetFields(projectID string) []domain.FieldLocation {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.FieldLocation(nil), s.fields[projectID]...)
}

func (s *Store) GetAssets(projectID string) []domain.EquipmentAsset {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.EquipmentAsset(nil), s.assets[projectID]...)
}

func (s *Store) GetPolicies(projectID string) []domain.AlertPolicy {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.AlertPolicy(nil), s.policies[projectID]...)
}

func (s *Store) GetProviders(projectID string) []domain.ProviderConnection {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.ProviderConnection(nil), s.providers[projectID]...)
}

func (s *Store) GetWeatherExchange(projectID string) ([]domain.ExchangeTokenInfo, []domain.WeatherExchangeRow) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.ExchangeTokenInfo(nil), s.exchangeTokens[projectID]...),
		append([]domain.WeatherExchangeRow(nil), s.weatherRows[projectID]...)
}

func (s *Store) SaveForecast(projectID string, bundle *domain.ProjectForecastBundle) {
	if bundle == nil {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.forecasts[projectID] = bundle
	_ = s.persistLocked()
}

func (s *Store) GetForecast(projectID string) *domain.ProjectForecastBundle {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.forecasts[projectID]
}

func (s *Store) GetAlertHistory(projectID string) []domain.AlertHistoryItem {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]domain.AlertHistoryItem(nil), s.alertHistory[projectID]...)
}

func (s *Store) ListIncidents(projectID, status string) []domain.Incident {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var out []domain.Incident
	for _, inc := range s.incidents {
		if projectID != "" && inc.ProjectID != projectID {
			continue
		}
		if status != "" && string(inc.Status) != status {
			continue
		}
		out = append(out, inc)
	}
	return out
}

func (s *Store) GetIncident(id string) (domain.Incident, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	inc, ok := s.incidents[id]
	return inc, ok
}

func (s *Store) UpdateIncident(inc domain.Incident) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.incidents[inc.ID]; !ok {
		return domain.ErrNotFound
	}
	s.incidents[inc.ID] = inc
	return s.persistLocked()
}

func (s *Store) AppendAudit(entry domain.AuditEntry) {
	s.mu.Lock()
	defer s.mu.Unlock()
	prevHash := "GENESIS"
	if n := len(s.auditLog); n > 0 && s.auditLog[n-1].EntryHash != "" {
		prevHash = s.auditLog[n-1].EntryHash
	}
	entry.PrevHash = prevHash
	entry.EntryHash = security.ComputeAuditHash(prevHash, entry)
	s.auditLog = append(s.auditLog, entry)
	if len(s.auditLog) > 1000 {
		s.auditLog = s.auditLog[len(s.auditLog)-1000:]
	}
	_ = s.persistLocked()
}

func (s *Store) VerifyAuditChain() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return security.VerifyAuditChain(s.auditLog)
}

func (s *Store) AuditCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.auditLog)
}

func (s *Store) EncryptionEnabled() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.cipher != nil
}

func (s *Store) ListAudit(limit int) []domain.AuditEntry {
	s.mu.RLock()
	defer s.mu.RUnlock()
	total := len(s.auditLog)
	if limit <= 0 || limit > total {
		limit = total
	}
	out := make([]domain.AuditEntry, 0, limit)
	for i := total - 1; i >= total-limit; i-- {
		out = append(out, s.auditLog[i])
	}
	return out
}

func (s *Store) SetSyncStatus(status domain.SyncStatus) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.syncStatus = status
	_ = s.persistLocked()
}

func (s *Store) GetSyncStatus() domain.SyncStatus {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.syncStatus
}
