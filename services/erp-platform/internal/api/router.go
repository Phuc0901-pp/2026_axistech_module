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

	// ISO Authentication API & Login Page
	mux.HandleFunc("POST /api/auth/login", h.PostAuthLogin)
	mux.HandleFunc("POST /api/auth/logout", h.PostAuthLogout)
	mux.HandleFunc("GET /api/auth/me", h.GetAuthMe)
	serveLoginView := func(w http.ResponseWriter, r *http.Request) {
		raw, err := fs.ReadFile(staticFiles, "static/login.html")
		if err != nil {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(raw)
	}
	mux.HandleFunc("GET /login", serveLoginView)
	mux.HandleFunc("GET /tbsgagtech/v1/login", serveLoginView)

	// Portable ISO 27001 encrypted REST endpoints (tbsgagtech namespace)
	mux.HandleFunc("GET /api/tbsgagtech/v1/modules/catalog", h.GetModulesCatalog)
	mux.HandleFunc("GET /api/tbsgagtech/v1/modules/devices/", h.GetDeviceModule)
	mux.HandleFunc("GET /api/tbsgagtech/v1/modules/forecast/", h.GetForecastModule)

	// Dedicated Isolated Standalone Module Pages (strip all ERP chrome)
	serveModuleView := func(w http.ResponseWriter, _ *http.Request) {
		raw, err := fs.ReadFile(staticFiles, "static/module-view.html")
		if err != nil {
			http.NotFound(w, nil)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(raw)
	}
	mux.HandleFunc("GET /tbsgagtech/v1/modules/devices/", serveModuleView)
	mux.HandleFunc("GET /tbsgagtech/v1/modules/forecast/", serveModuleView)

	// Deep-link ISO SPA routes (/tbsgagtech/v1/* admin ERP workspace)
	mux.HandleFunc("GET /tbsgagtech/", func(w http.ResponseWriter, r *http.Request) {
		raw, err := fs.ReadFile(staticFiles, "static/index.html")
		if err != nil {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(raw)
	})

	sub, err := fs.Sub(staticFiles, "static")
	if err == nil {
		mux.Handle("/", http.FileServer(http.FS(sub)))
	}

	return SecurityAndCorrelationMiddleware(log, mux, opts)
}
