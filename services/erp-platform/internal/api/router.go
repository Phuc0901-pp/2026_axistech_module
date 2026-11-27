package api

import (
	"embed"
	"io/fs"
	"log/slog"
	"net/http"
)

//go:embed static
var staticFiles embed.FS

// NewRouter builds the complete Go stdlib HTTP mux for the ERP API + embedded Dashboard UI.
func NewRouter(h *Handler, log *slog.Logger) http.Handler {
	return NewRouterWithOptions(h, log, RouterSecurityOptions{RateLimitRPM: 300})
}

// NewRouterWithOptions builds the ERP HTTP mux with custom ISO 27001 middleware options.
func NewRouterWithOptions(h *Handler, log *slog.Logger, opts RouterSecurityOptions) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health/live", h.HealthLive)
	mux.HandleFunc("GET /health/ready", h.HealthReady)

	mux.HandleFunc("GET /api/erp/v1/dashboard", h.GetDashboard)
	mux.HandleFunc("GET /api/erp/v1/security/status", h.GetSecurityStatus)
	mux.HandleFunc("GET /api/erp/v1/projects", h.ListProjects)
	mux.HandleFunc("GET /api/erp/v1/devices", h.ListDevices)
	mux.HandleFunc("GET /api/erp/v1/telemetry", h.GetTelemetry)
	mux.HandleFunc("GET /api/erp/v1/telemetry/history", h.GetTelemetryHistory)
	mux.HandleFunc("GET /api/erp/v1/fields", h.ListFields)
	mux.HandleFunc("GET /api/erp/v1/assets", h.ListAssets)
	mux.HandleFunc("GET /api/erp/v1/alerts/policies", h.ListAlertPolicies)
	mux.HandleFunc("GET /api/erp/v1/alerts/history", h.ListAlertHistory)
	mux.HandleFunc("GET /api/erp/v1/forecast", h.GetForecast)
	mux.HandleFunc("GET /api/erp/v1/incidents", h.ListIncidents)
	mux.HandleFunc("POST /api/erp/v1/incidents/", h.IncidentAction)
	mux.HandleFunc("GET /api/erp/v1/exchange/weather", h.GetWeatherExchange)
	mux.HandleFunc("GET /api/erp/v1/exchange/weather/export.csv", h.ExportWeatherCSV)
	mux.HandleFunc("GET /api/erp/v1/audit", h.ListAudit)
	mux.HandleFunc("POST /api/erp/v1/sync/now", h.TriggerSync)
	mux.HandleFunc("GET /api/erp/v1/events", h.StreamEvents)

	sub, err := fs.Sub(staticFiles, "static")
	if err == nil {
		mux.Handle("/", http.FileServer(http.FS(sub)))
	}

	return SecurityAndCorrelationMiddleware(log, mux, opts)
}
