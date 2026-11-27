package domain

import "time"

type Organisation struct {
	ID           string  `json:"id"`
	Name         string  `json:"name"`
	SchemaName   string  `json:"schema_name"`
	PBIWorkspace *string `json:"pbi_workspace,omitempty"`
}

type ProjectAccess struct {
	HQ        []string `json:"hq"`
	My        []string `json:"my"`
	FM4D      []string `json:"fm4d"`
	Users     []string `json:"users"`
	FieldApp  []string `json:"field_app"`
	Resources []string `json:"resources"`
}

type Project struct {
	ID           string        `json:"id"`
	Name         string        `json:"name"`
	Description  string        `json:"description"`
	Role         string        `json:"role"`
	Organisation Organisation  `json:"organisation"`
	Access       ProjectAccess `json:"access"`
}

type Coordinates struct {
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type Device struct {
	ID           string       `json:"id"`
	Name         string       `json:"name"`
	Description  string       `json:"description"`
	ExternalID   string       `json:"external_id"`
	SourceCode   string       `json:"source_code"`
	SensorSet    string       `json:"sensor_set_code"`
	CommType     string       `json:"comm_type"`
	Active       bool         `json:"active"`
	PreferredUOM string       `json:"preferred_uom"`
	Coordinates  *Coordinates `json:"coordinates,omitempty"`
	UpdatedAt    *time.Time   `json:"updated_at,omitempty"`
}

type TelemetryReading struct {
	DeviceID     string    `json:"device_id"`
	ExternalID   string    `json:"external_id"`
	SourceCode   string    `json:"source_code"`
	Metric       string    `json:"metric"`
	Value        *float64  `json:"value"`
	Unit         string    `json:"unit"`
	DepthLevel   *int      `json:"depth_level,omitempty"`
	TimestampUTC time.Time `json:"timestamp_utc"`
}

type DeviceMetadata struct {
	LastReportedUTC   *time.Time `json:"last_reported_utc,omitempty"`
	BatteryLevel      *float64   `json:"battery_level,omitempty"`
	SignalStrengthDBM *float64   `json:"signal_strength_dbm,omitempty"`
	ReadingInterval   *string    `json:"reading_interval,omitempty"`
}

type DeviceSnapshot struct {
	DeviceID           string             `json:"device_id"`
	ExternalID         string             `json:"external_id"`
	SourceCode         string             `json:"source_code"`
	Status             string             `json:"status"` // LIVE, LATE, OFFLINE, NO_DATA
	LatestTimestampUTC *time.Time         `json:"latest_timestamp_utc,omitempty"`
	Readings           []TelemetryReading `json:"readings"`
	Metadata           DeviceMetadata     `json:"metadata"`
	UOM                map[string]string  `json:"uom"`
}

type GeoPolygonSite struct {
	ID       string         `json:"id"`
	Name     string         `json:"name"`
	Category string         `json:"category"`
	GeoJSON  map[string]any `json:"geojson,omitempty"`
	Area     *float64       `json:"area,omitempty"`
}

type FieldLocation struct {
	ID        string           `json:"id"`
	ProjectID string           `json:"project_id"`
	Name      string           `json:"name"`
	Category  string           `json:"category"`
	Address   string           `json:"address"`
	IsDefault bool             `json:"is_default"`
	Sites     []GeoPolygonSite `json:"sites"`
}

type EquipmentAsset struct {
	ID             string       `json:"id"`
	ProjectID      string       `json:"project_id"`
	Name           string       `json:"name"`
	AssetType      string       `json:"asset_type"`
	Description    string       `json:"description"`
	Make           string       `json:"make"`
	Model          string       `json:"model"`
	NumberPlate    *string      `json:"number_plate,omitempty"`
	CapacityLitres *float64     `json:"capacity_litres,omitempty"`
	Position       *Coordinates `json:"position,omitempty"`
}

type AlertCondition struct {
	Name          string `json:"name"`
	ConditionType string `json:"condition_type"`
	Column        string `json:"column"`
	Operator      string `json:"operator"`
	Threshold     string `json:"threshold"`
}

type AlertPolicy struct {
	ID                     string           `json:"id"`
	ProjectID              string           `json:"project_id"`
	Name                   string           `json:"name"`
	EntityID               string           `json:"entity_id"`
	DeviceName             string           `json:"device_name"`
	Status                 string           `json:"status"`
	Priority               string           `json:"priority"`
	FrequencyWindowMinutes int              `json:"frequency_window_minutes"`
	NotificationTypes      []string         `json:"notification_types"`
	Conditions             []AlertCondition `json:"conditions"`
	MessageTemplate        string           `json:"message_template"`
}

type AlertHistoryItem struct {
	ID                string     `json:"id"`
	ProjectID         string     `json:"project_id"`
	PolicyName        string     `json:"policy_name"`
	DeviceName        string     `json:"device_name"`
	RuleDescription   string     `json:"rule_description"`
	DeliveryStatus    string     `json:"delivery_status"`
	NotificationCount int        `json:"notification_count"`
	TriggeredAtUTC    *time.Time `json:"triggered_at_utc,omitempty"`
}

type ProviderConnection struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Code   string `json:"code"`
	Status string `json:"status"`
}

type ExchangeDataset struct {
	TableID    string   `json:"table_id"`
	TableName  string   `json:"table_name"`
	SchemaName string   `json:"schema_name"`
	Columns    []string `json:"columns"`
}

type ExchangeTokenInfo struct {
	TokenID               string            `json:"token_id"`
	Name                  string            `json:"name"`
	Status                string            `json:"status"`
	ValidUntilUTC         *time.Time        `json:"valid_until_utc,omitempty"`
	DefaultRowsPerRequest int               `json:"default_rows_per_request"`
	UnrestrictedDevices   bool              `json:"unrestricted_devices"`
	Datasets              []ExchangeDataset `json:"datasets"`
}

type WeatherExchangeRow struct {
	Code             string    `json:"code"`
	Time             time.Time `json:"time"`
	TemperatureAvg   *float64  `json:"temperature_avg"`
	HumidityAvg      *float64  `json:"humidity_avg"`
	DeltaTAvg        *float64  `json:"deltat_avg"`
	DewpointAvg      *float64  `json:"dewpoint_avg"`
	AtmosPressureAvg *float64  `json:"atmos_pressure_avg"`
	MSLPressure      *float64  `json:"msl_pressure"`
	Rainfall         *float64  `json:"rainfall"`
	RainfallTotal    *float64  `json:"rainfall_total"`
	WindSpeedAvg     *float64  `json:"wind_speed_avg"`
	WindSpeedMin     *float64  `json:"wind_speed_min"`
	WindSpeedMax     *float64  `json:"wind_speed_max"`
	WindDirDegAvg    *float64  `json:"wind_dir_deg_avg"`
	WindDirVarAvg    *float64  `json:"wind_dir_var_avg"`
	SolarRadAvg      *float64  `json:"solar_rad_avg"`
	UVIndexAvg       *float64  `json:"uv_index_avg"`
}

type IncidentStatus string

const (
	IncidentOpen         IncidentStatus = "OPEN"
	IncidentAcknowledged IncidentStatus = "ACKNOWLEDGED"
	IncidentResolved     IncidentStatus = "RESOLVED"
)

type Incident struct {
	ID             string         `json:"id"`
	ProjectID      string         `json:"project_id"`
	PolicyName     string         `json:"policy_name"`
	DeviceID       string         `json:"device_id"`
	DeviceName     string         `json:"device_name"`
	Severity       string         `json:"severity"`
	Status         IncidentStatus `json:"status"`
	Message        string         `json:"message"`
	AcknowledgedBy string         `json:"acknowledged_by,omitempty"`
	ResolvedBy     string         `json:"resolved_by,omitempty"`
	Notes          string         `json:"notes,omitempty"`
	CreatedAtUTC   time.Time      `json:"created_at_utc"`
	UpdatedAtUTC   time.Time      `json:"updated_at_utc"`
}

type AuditEntry struct {
	ID            string    `json:"id"`
	TimestampUTC  time.Time `json:"timestamp_utc"`
	Actor         string    `json:"actor"`
	Action        string    `json:"action"`
	ResourceType  string    `json:"resource_type"`
	ResourceID    string    `json:"resource_id"`
	CorrelationID string    `json:"correlation_id"`
	Details       string    `json:"details"`
	PrevHash      string    `json:"prev_hash,omitempty"`
	EntryHash     string    `json:"entry_hash,omitempty"`
}

type SecurityPosture struct {
	EncryptionAtRest    bool   `json:"encryption_at_rest"`
	EncryptionAlgorithm string `json:"encryption_algorithm"`
	AuditChainVerified  bool   `json:"audit_chain_verified"`
	AuditEntries        int    `json:"audit_entries"`
	RateLimitRPM        int    `json:"rate_limit_rpm"`
	APIKeyGuardEnabled  bool   `json:"api_key_guard_enabled"`
	ReadOnlyCloudSync   bool   `json:"read_only_cloud_sync"`
	CSPPolicy           string `json:"csp_policy"`
}

type SyncStatus struct {
	LastSyncUTC  *time.Time `json:"last_sync_utc,omitempty"`
	SyncCount    int64      `json:"sync_count"`
	BridgeHealth string     `json:"bridge_health"`
	LastError    string     `json:"last_error,omitempty"`
}

type ForecastLocation struct {
	Name             string   `json:"name"`
	Latitude         *float64 `json:"latitude,omitempty"`
	Longitude        *float64 `json:"longitude,omitempty"`
	Elevation        *float64 `json:"elevation,omitempty"`
	TimeZone         string   `json:"time_zone"`
	UTCOffsetMinutes *int     `json:"utc_offset_minutes,omitempty"`
}

type ForecastDay struct {
	Date           string   `json:"date"`
	Complete       bool     `json:"complete"`
	HoursCovered   *int     `json:"hours_covered,omitempty"`
	TemperatureMin *float64 `json:"temperature_min,omitempty"`
	TemperatureMax *float64 `json:"temperature_max,omitempty"`
	Precipitation  *float64 `json:"precipitation,omitempty"`
	Symbol         string   `json:"symbol"`
	RainProb       *float64 `json:"rain_prob,omitempty"`
	WindMax        *float64 `json:"wind_max,omitempty"`
	UVMax          *float64 `json:"uv_max,omitempty"`
	SolarTotal     *float64 `json:"solar_total,omitempty"`
	ET0            *float64 `json:"et0,omitempty"`
	Summary        string   `json:"summary"`
}

type ForecastStep struct {
	TimeUTC          time.Time `json:"time_utc"`
	TimeLocal        string    `json:"time_local"`
	IntervalHours    int       `json:"interval_hours"`
	IsNight          bool      `json:"is_night"`
	Temperature      *float64  `json:"temperature,omitempty"`
	FeelsLike        *float64  `json:"feels_like,omitempty"`
	DewPoint         *float64  `json:"dew_point,omitempty"`
	DeltaT           *float64  `json:"delta_t,omitempty"`
	Humidity         *float64  `json:"humidity,omitempty"`
	Pressure         *float64  `json:"pressure,omitempty"`
	WindSpeed        *float64  `json:"wind_speed,omitempty"`
	WindGust         *float64  `json:"wind_gust,omitempty"`
	WindDirection    *float64  `json:"wind_direction,omitempty"`
	UVIndex          *float64  `json:"uv_index,omitempty"`
	CloudCover       *float64  `json:"cloud_cover,omitempty"`
	CloudCoverLow    *float64  `json:"cloud_cover_low,omitempty"`
	CloudCoverMedium *float64  `json:"cloud_cover_medium,omitempty"`
	CloudCoverHigh   *float64  `json:"cloud_cover_high,omitempty"`
	Fog              *float64  `json:"fog,omitempty"`
	Precipitation1h  *float64  `json:"precipitation_1h,omitempty"`
	Precipitation6h  *float64  `json:"precipitation_6h,omitempty"`
	RainProb         *float64  `json:"rain_prob,omitempty"`
	Symbol           string    `json:"symbol"`
}

type SprayHour struct {
	TimeUTC       time.Time `json:"time_utc"`
	Status        string    `json:"status"`
	DeltaT        *float64  `json:"delta_t,omitempty"`
	WindSpeed     *float64  `json:"wind_speed,omitempty"`
	RainProb      *float64  `json:"rain_prob,omitempty"`
	InversionRisk string    `json:"inversion_risk"`
	Reasons       []string  `json:"reasons"`
}

type SprayWindow struct {
	StartUTC      time.Time `json:"start_utc"`
	EndUTC        time.Time `json:"end_utc"`
	DurationHours *float64  `json:"duration_hours,omitempty"`
	Quality       string    `json:"quality"`
}

type WeatherForecastReport struct {
	Provider         string            `json:"provider"`
	Status           string            `json:"status"`
	Location         *ForecastLocation `json:"location,omitempty"`
	UpdatedAtUTC     *time.Time        `json:"updated_at_utc,omitempty"`
	ExpiresAtUTC     *time.Time        `json:"expires_at_utc,omitempty"`
	CurrentStepIndex int               `json:"current_step_index"`
	Days             []ForecastDay     `json:"days"`
	Steps            []ForecastStep    `json:"steps"`
	SprayHours       []SprayHour       `json:"spray_hours"`
	SprayWindows     []SprayWindow     `json:"spray_windows"`
	ErrorMessage     string            `json:"error_message"`
}

type ProjectForecastBundle struct {
	ProjectID    string                `json:"project_id"`
	MetNorway    WeatherForecastReport `json:"met_norway"`
	JanesWeather WeatherForecastReport `json:"janes_weather"`
}

type DashboardSummary struct {
	ActiveProjectID string                        `json:"active_project_id"`
	Projects        []Project                     `json:"projects"`
	TotalDevices    int                           `json:"total_devices"`
	LiveDevices     int                           `json:"live_devices"`
	NoDataDevices   int                           `json:"no_data_devices"`
	OfflineDevices  int                           `json:"offline_devices"`
	TotalFields     int                           `json:"total_fields"`
	TotalAssets     int                           `json:"total_assets"`
	OpenIncidents   int                           `json:"open_incidents"`
	AckIncidents    int                           `json:"acknowledged_incidents"`
	ActivePolicies  int                           `json:"active_policies"`
	ExchangeRows    int                           `json:"exchange_rows"`
	LatestWeather   map[string]float64            `json:"latest_weather"`
	Snapshots       []DeviceSnapshot              `json:"snapshots"`
	Devices         []Device                      `json:"devices"`
	SyncStatus      SyncStatus                    `json:"sync_status"`
	ISOCompliance   map[string]string             `json:"iso_compliance"`
	Providers       []ProviderConnection          `json:"providers"`
	Forecast        *ProjectForecastBundle        `json:"forecast,omitempty"`
	Security        SecurityPosture               `json:"security"`
}
