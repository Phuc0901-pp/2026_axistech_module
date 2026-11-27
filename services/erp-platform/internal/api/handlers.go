package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/realtime"
	"github.com/tanbaocorp/axisstream-erp/internal/repository"
	"github.com/tanbaocorp/axisstream-erp/internal/security"
	"github.com/tanbaocorp/axisstream-erp/internal/service"
)

type Handler struct {
	svc    *service.ERPService
	store  *repository.Store
	hub    *realtime.Hub
	log    *slog.Logger
	tokens *security.ResourceTokenCodec
	auth   *security.AuthManager
}

func NewHandler(svc *service.ERPService, store *repository.Store, hub *realtime.Hub, log *slog.Logger) *Handler {
	return &Handler{
		svc:    svc,
		store:  store,
		hub:    hub,
		log:    log,
		tokens: security.NewResourceTokenCodec(""),
		auth:   security.NewAuthManager(""),
	}
}

func (h *Handler) SetTokenCodec(codec *security.ResourceTokenCodec) {
	if codec != nil {
		h.tokens = codec
	}
}

func (h *Handler) SetAuthManager(am *security.AuthManager) {
	if am != nil {
		h.auth = am
	}
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func (h *Handler) resolveProjectID(r *http.Request) string {
	pid := strings.TrimSpace(r.URL.Query().Get("project_id"))
	if pid != "" {
		return pid
	}
	projects := h.store.GetProjects()
	if len(projects) > 0 {
		return projects[0].ID
	}
	return ""
}

func (h *Handler) HealthLive(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "UP"})
}

func (h *Handler) HealthReady(w http.ResponseWriter, _ *http.Request) {
	st := h.store.GetSyncStatus()
	code := http.StatusOK
	status := "READY"
	if st.BridgeHealth == "DOWN" {
		code = http.StatusServiceUnavailable
		status = "DEGRADED"
	}
	writeJSON(w, code, map[string]any{
		"status":        status,
		"bridge_health": st.BridgeHealth,
		"sync_count":    st.SyncCount,
	})
}

func (h *Handler) GetDashboard(w http.ResponseWriter, r *http.Request) {
	pid := strings.TrimSpace(r.URL.Query().Get("project_id"))
	writeJSON(w, http.StatusOK, h.svc.GetDashboard(pid))
}

func (h *Handler) GetSecurityStatus(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, h.svc.GetSecurityPosture())
}

func (h *Handler) ListProjects(w http.ResponseWriter, _ *http.Request) {
	projects := h.store.GetProjects()
	writeJSON(w, http.StatusOK, map[string]any{"data": projects, "count": len(projects)})
}

func (h *Handler) ListDevices(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	devices := h.store.GetDevices(pid)
	writeJSON(w, http.StatusOK, map[string]any{"data": devices, "count": len(devices)})
}

func (h *Handler) GetTelemetry(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	did := strings.TrimSpace(r.URL.Query().Get("device_id"))
	snaps := h.store.GetSnapshots(pid)
	readings := h.store.GetReadings(pid, did)
	writeJSON(w, http.StatusOK, map[string]any{
		"snapshots": snaps,
		"readings":  readings,
		"count":     len(readings),
	})
}

func (h *Handler) GetTelemetryHistory(w http.ResponseWriter, r *http.Request) {
	cid := GetCorrelationID(r.Context())
	pid := h.resolveProjectID(r)
	did := strings.TrimSpace(r.URL.Query().Get("device_id"))
	hours := 24
	if raw := strings.TrimSpace(r.URL.Query().Get("hours")); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 {
			if parsed > 720 {
				parsed = 720
			}
			hours = parsed
		}
	}
	rows := h.svc.GetTelemetryHistory(r.Context(), pid, did, hours, cid)
	writeJSON(w, http.StatusOK, map[string]any{
		"project_id": pid,
		"device_id":  did,
		"hours":      hours,
		"data":       rows,
		"count":      len(rows),
	})
}

func (h *Handler) ListFields(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	fields := h.store.GetFields(pid)
	writeJSON(w, http.StatusOK, map[string]any{"data": fields, "count": len(fields)})
}

func (h *Handler) ListAssets(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	assets := h.store.GetAssets(pid)
	writeJSON(w, http.StatusOK, map[string]any{"data": assets, "count": len(assets)})
}

func (h *Handler) ListAlertPolicies(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	policies := h.store.GetPolicies(pid)
	writeJSON(w, http.StatusOK, map[string]any{"data": policies, "count": len(policies)})
}

func (h *Handler) ListAlertHistory(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	items := h.store.GetAlertHistory(pid)
	writeJSON(w, http.StatusOK, map[string]any{"data": items, "count": len(items)})
}

func (h *Handler) GetForecast(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	bundle := h.store.GetForecast(pid)
	if bundle == nil {
		bundle = &domain.ProjectForecastBundle{
			ProjectID:    pid,
			MetNorway:    domain.WeatherForecastReport{Provider: "MET Norway", Status: "DISCONNECTED"},
			JanesWeather: domain.WeatherForecastReport{Provider: "Jane's Weather", Status: "DISCONNECTED"},
		}
	}
	writeJSON(w, http.StatusOK, bundle)
}

func (h *Handler) ListIncidents(w http.ResponseWriter, r *http.Request) {
	pid := strings.TrimSpace(r.URL.Query().Get("project_id"))
	status := strings.TrimSpace(r.URL.Query().Get("status"))
	items := h.store.ListIncidents(pid, status)
	writeJSON(w, http.StatusOK, map[string]any{"data": items, "count": len(items)})
}

type incidentActionReq struct {
	Actor string `json:"actor"`
	Notes string `json:"notes"`
}

func (h *Handler) IncidentAction(w http.ResponseWriter, r *http.Request) {
	cid := GetCorrelationID(r.Context())
	// Path: /api/erp/v1/incidents/{id}/{action}
	trimmed := strings.TrimPrefix(r.URL.Path, "/api/erp/v1/incidents/")
	parts := strings.Split(strings.Trim(trimmed, "/"), "/")
	if len(parts) != 2 || parts[0] == "" {
		WriteProblemJSON(w, http.StatusNotFound, "NOT_FOUND", "Invalid incident endpoint path", cid)
		return
	}
	incID, action := parts[0], parts[1]

	var body incidentActionReq
	if r.Body != nil {
		_ = json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&body)
	}

	var (
		updated domain.Incident
		err     error
	)
	switch action {
	case "acknowledge":
		updated, err = h.svc.AcknowledgeIncident(incID, body.Actor, body.Notes, cid)
	case "resolve":
		updated, err = h.svc.ResolveIncident(incID, body.Actor, body.Notes, cid)
	default:
		WriteProblemJSON(w, http.StatusNotFound, "NOT_FOUND", "Unsupported incident action", cid)
		return
	}

	if err != nil {
		switch {
		case errors.Is(err, domain.ErrNotFound):
			WriteProblemJSON(w, http.StatusNotFound, "INCIDENT_NOT_FOUND", err.Error(), cid)
		case errors.Is(err, domain.ErrInvalidTransition):
			WriteProblemJSON(w, http.StatusConflict, "INVALID_TRANSITION", err.Error(), cid)
		default:
			WriteProblemJSON(w, http.StatusInternalServerError, "INTERNAL_ERROR", err.Error(), cid)
		}
		return
	}
	writeJSON(w, http.StatusOK, updated)
}

func (h *Handler) GetWeatherExchange(w http.ResponseWriter, r *http.Request) {
	pid := h.resolveProjectID(r)
	tokens, rows := h.store.GetWeatherExchange(pid)
	writeJSON(w, http.StatusOK, map[string]any{
		"tokens": tokens,
		"data":   rows,
		"count":  len(rows),
	})
}

func (h *Handler) ExportWeatherCSV(w http.ResponseWriter, r *http.Request) {
	cid := GetCorrelationID(r.Context())
	pid := h.resolveProjectID(r)
	csvBytes, err := h.svc.ExportWeatherCSV(pid)
	if err != nil {
		WriteProblemJSON(w, http.StatusInternalServerError, "CSV_EXPORT_ERROR", err.Error(), cid)
		return
	}
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="tbncorp_weather_exchange.csv"`)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(csvBytes)
}

func (h *Handler) ListAudit(w http.ResponseWriter, r *http.Request) {
	limit := 100
	if l := r.URL.Query().Get("limit"); l != "" {
		if parsed, err := strconv.Atoi(l); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	entries := h.store.ListAudit(limit)
	writeJSON(w, http.StatusOK, map[string]any{"data": entries, "count": len(entries)})
}

func (h *Handler) TriggerSync(w http.ResponseWriter, r *http.Request) {
	cid := GetCorrelationID(r.Context())
	if err := h.svc.ForceSyncNow(r.Context(), cid); err != nil {
		WriteProblemJSON(w, http.StatusBadGateway, "BRIDGE_SYNC_FAILED", err.Error(), cid)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "SYNCED", "correlation_id": cid})
}

func (h *Handler) StreamEvents(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		WriteProblemJSON(w, http.StatusInternalServerError, "STREAMING_UNSUPPORTED", "Streaming unsupported", GetCorrelationID(r.Context()))
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	ch, unsub := h.hub.Subscribe()
	defer unsub()

	_, _ = fmt.Fprint(w, "event: connected\ndata: {\"status\":\"connected\"}\n\n")
	flusher.Flush()

	heartbeat := time.NewTicker(15 * time.Second)
	defer heartbeat.Stop()

	for {
		select {
		case <-r.Context().Done():
			return
		case ev, open := <-ch:
			if !open {
				return
			}
			_, _ = fmt.Fprint(w, ev.FormatSSE())
			flusher.Flush()
		case <-heartbeat.C:
			_, _ = fmt.Fprint(w, "event: heartbeat\ndata: {\"status\":\"alive\"}\n\n")
			flusher.Flush()
		}
	}
}

func parsePageParams(r *http.Request, defaultSize int) (int, int) {
	page := 1
	pageSize := defaultSize
	if raw := strings.TrimSpace(r.URL.Query().Get("page")); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v > 0 {
			page = v
		}
	}
	if raw := strings.TrimSpace(r.URL.Query().Get("page_size")); raw != "" {
		if v, err := strconv.Atoi(raw); err == nil && v > 0 {
			if v > 100 {
				v = 100
			}
			pageSize = v
		}
	}
	return page, pageSize
}

func resolveForecastPoint(bundle *domain.ProjectForecastBundle, devices []domain.Device) (string, *float64, *float64, *float64, string) {
	if bundle != nil && bundle.MetNorway.Location != nil && bundle.MetNorway.Location.Latitude != nil && bundle.MetNorway.Location.Longitude != nil {
		return bundle.MetNorway.Location.Name, bundle.MetNorway.Location.Latitude, bundle.MetNorway.Location.Longitude, bundle.MetNorway.Location.Elevation, bundle.MetNorway.Location.TimeZone
	}
	for _, d := range devices {
		if d.Coordinates != nil {
			lat, lon := d.Coordinates.Latitude, d.Coordinates.Longitude
			return d.Name, &lat, &lon, nil, "UTC"
		}
	}
	return "", nil, nil, nil, "UTC"
}

func (h *Handler) GetModulesCatalog(w http.ResponseWriter, _ *http.Request) {
	type deviceCatalogItem struct {
		Token       string `json:"token"`
		ProjectID   string `json:"project_id"`
		ProjectName string `json:"project_name"`
		DeviceID    string `json:"device_id"`
		Name        string `json:"name"`
		SourceCode  string `json:"source_code"`
		Active      bool   `json:"active"`
		UIURL       string `json:"ui_url"`
		EmbedURL    string `json:"embed_url"`
		APIURL      string `json:"api_url"`
	}
	type forecastCatalogItem struct {
		Token       string   `json:"token"`
		ProjectID   string   `json:"project_id"`
		ProjectName string   `json:"project_name"`
		Name        string   `json:"name"`
		Latitude    *float64 `json:"latitude,omitempty"`
		Longitude   *float64 `json:"longitude,omitempty"`
		UIURL       string   `json:"ui_url"`
		EmbedURL    string   `json:"embed_url"`
		APIURL      string   `json:"api_url"`
	}

	devItems := make([]deviceCatalogItem, 0)
	fcItems := make([]forecastCatalogItem, 0)

	for _, p := range h.store.GetProjects() {
		devs := h.store.GetDevices(p.ID)
		for _, d := range devs {
			tok, err := h.tokens.EncodeDeviceToken(p.ID, d.ID)
			if err != nil {
				continue
			}
			uiURL := "/tbsgagtech/v1/modules/devices/" + tok
			devItems = append(devItems, deviceCatalogItem{
				Token:       tok,
				ProjectID:   p.ID,
				ProjectName: p.Name,
				DeviceID:    d.ID,
				Name:        d.Name,
				SourceCode:  d.SourceCode,
				Active:      d.Active,
				UIURL:       uiURL,
				EmbedURL:    uiURL + "?embed=1",
				APIURL:      "/api/tbsgagtech/v1/modules/devices/" + tok,
			})
		}

		bundle := h.store.GetForecast(p.ID)
		name, lat, lon, _, _ := resolveForecastPoint(bundle, devs)
		if lat != nil && lon != nil {
			tok, err := h.tokens.EncodeForecastToken(p.ID, *lat, *lon)
			if err == nil {
				if name == "" {
					name = p.Name + " Forecast"
				}
				uiURL := "/tbsgagtech/v1/modules/forecast/" + tok
				fcItems = append(fcItems, forecastCatalogItem{
					Token:       tok,
					ProjectID:   p.ID,
					ProjectName: p.Name,
					Name:        name,
					Latitude:    lat,
					Longitude:   lon,
					UIURL:       uiURL,
					EmbedURL:    uiURL + "?embed=1",
					APIURL:      "/api/tbsgagtech/v1/modules/forecast/" + tok,
				})
			}
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"namespace": "tbsgagtech",
		"standard":  "ISO-42010/ISO-27001/RFC-4648",
		"devices":   devItems,
		"forecasts": fcItems,
	})
}

func (h *Handler) GetDeviceModule(w http.ResponseWriter, r *http.Request) {
	cid := GetCorrelationID(r.Context())
	token := strings.TrimPrefix(r.URL.Path, "/api/tbsgagtech/v1/modules/devices/")
	token = strings.Trim(token, "/")
	projectID, deviceID, err := h.tokens.DecodeDeviceToken(token)
	if err != nil {
		WriteProblemJSON(w, http.StatusBadRequest, "INVALID_RESOURCE_TOKEN", err.Error(), cid)
		return
	}

	var dev *domain.Device
	for _, d := range h.store.GetDevices(projectID) {
		if d.ID == deviceID {
			copyDev := d
			dev = &copyDev
			break
		}
	}
	if dev == nil {
		WriteProblemJSON(w, http.StatusNotFound, "DEVICE_NOT_FOUND", "device not found for resource token", cid)
		return
	}

	var snap *domain.DeviceSnapshot
	for _, s := range h.store.GetSnapshots(projectID) {
		if s.DeviceID == deviceID {
			copySnap := s
			snap = &copySnap
			break
		}
	}

	powerLabel := "OFF"
	powerReason := "No Signal"
	if !dev.Active {
		powerReason = "Disabled"
	} else if snap != nil && snap.Status == "LIVE" && snap.LatestTimestampUTC != nil {
		age := time.Since(snap.LatestTimestampUTC.UTC())
		if age <= 6*time.Hour {
			powerLabel = "ON"
			powerReason = "Active"
		} else {
			powerReason = fmt.Sprintf("Offline %dh ago", int(age.Hours()))
		}
	}

	requestedMetric := strings.TrimSpace(r.URL.Query().Get("metric"))
	history := h.svc.GetTelemetryHistory(r.Context(), projectID, deviceID, 24, cid)
	if len(history) == 0 && snap != nil {
		history = snap.Readings
	}

	metricSet := make(map[string]struct{})
	for _, rd := range history {
		if rd.Metric != "" {
			metricSet[rd.Metric] = struct{}{}
		}
	}
	availableMetrics := make([]string, 0, len(metricSet))
	for m := range metricSet {
		availableMetrics = append(availableMetrics, m)
	}
	sort.Strings(availableMetrics)

	filtered := make([]domain.TelemetryReading, 0, len(history))
	selectedMetric := requestedMetric
	if selectedMetric == "" && len(availableMetrics) > 0 {
		selectedMetric = availableMetrics[0]
	}
	unit := ""
	for _, rd := range history {
		if selectedMetric == "" && rd.Metric != "" {
			selectedMetric = rd.Metric
		}
		if selectedMetric == "" || rd.Metric == selectedMetric {
			if unit == "" {
				unit = rd.Unit
			}
			filtered = append(filtered, rd)
		}
	}

	page, pageSize := parsePageParams(r, 10)
	total := len(filtered)
	start := (page - 1) * pageSize
	if start > total {
		start = total
	}
	end := start + pageSize
	if end > total {
		end = total
	}

	type seriesPoint struct {
		TimeUTC string  `json:"t"`
		Value   float64 `json:"v"`
	}
	pts := make([]seriesPoint, 0, len(filtered))
	for _, rd := range filtered {
		if rd.Value != nil {
			pts = append(pts, seriesPoint{TimeUTC: rd.TimestampUTC.UTC().Format(time.RFC3339), Value: *rd.Value})
		}
	}

	var devMeta *domain.DeviceMetadata
	if snap != nil {
		mCopy := snap.Metadata
		devMeta = &mCopy
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"namespace":         "tbsgagtech",
		"token":             token,
		"ui_url":            "/tbsgagtech/v1/modules/devices/" + token,
		"embed_url":         "/tbsgagtech/v1/modules/devices/" + token + "?embed=1",
		"device":            dev,
		"metadata":          devMeta,
		"power_state":       map[string]string{"status": powerLabel, "reason": powerReason},
		"available_metrics": availableMetrics,
		"geolocation":       map[string]any{"coordinates": dev.Coordinates, "fields": h.store.GetFields(projectID)},
		"table":             map[string]any{"page": page, "page_size": pageSize, "total": total, "rows": filtered[start:end]},
		"chart":             map[string]any{"metric": selectedMetric, "unit": unit, "points": pts},
	})
}

func (h *Handler) GetForecastModule(w http.ResponseWriter, r *http.Request) {
	cid := GetCorrelationID(r.Context())
	token := strings.TrimPrefix(r.URL.Path, "/api/tbsgagtech/v1/modules/forecast/")
	token = strings.Trim(token, "/")
	projectID, lat, lon, err := h.tokens.DecodeForecastToken(token)
	if err != nil {
		WriteProblemJSON(w, http.StatusBadRequest, "INVALID_RESOURCE_TOKEN", err.Error(), cid)
		return
	}

	bundle := h.store.GetForecast(projectID)
	if bundle == nil {
		WriteProblemJSON(w, http.StatusNotFound, "FORECAST_NOT_FOUND", "forecast not cached for project", cid)
		return
	}

	metric := strings.TrimSpace(r.URL.Query().Get("metric"))
	if metric == "" {
		metric = "temperature"
	}
	unit := "°C"
	chartType := "line"
	pickVal := func(st domain.ForecastStep) *float64 {
		switch metric {
		case "feels_like":
			unit = "°C"
			return st.FeelsLike
		case "dew_point":
			unit = "°C"
			return st.DewPoint
		case "precipitation_1h":
			unit = "mm"
			chartType = "bar"
			if st.Precipitation1h != nil {
				return st.Precipitation1h
			}
			return st.Precipitation6h
		case "humidity":
			unit = "%"
			return st.Humidity
		case "wind_speed":
			unit = "km/h"
			return st.WindSpeed
		case "pressure":
			unit = "hPa"
			return st.Pressure
		case "cloud_cover":
			unit = "%"
			return st.CloudCover
		case "uv_index":
			unit = "UV"
			return st.UVIndex
		default:
			metric = "temperature"
			unit = "°C"
			return st.Temperature
		}
	}

	steps := bundle.MetNorway.Steps
	type forecastRow struct {
		TimeUTC  string   `json:"time_utc"`
		TimeLoc  string   `json:"time_local"`
		Symbol   string   `json:"symbol"`
		Value    *float64 `json:"value"`
		Unit     string   `json:"unit"`
		Rain1h   *float64 `json:"precipitation_1h,omitempty"`
		WindKmh  *float64 `json:"wind_speed,omitempty"`
	}
	type seriesPoint struct {
		TimeUTC string  `json:"t"`
		Value   float64 `json:"v"`
	}
	allRows := make([]forecastRow, 0, len(steps))
	pts := make([]seriesPoint, 0, len(steps))
	for _, st := range steps {
		v := pickVal(st)
		allRows = append(allRows, forecastRow{
			TimeUTC: st.TimeUTC.UTC().Format(time.RFC3339),
			TimeLoc: st.TimeLocal,
			Symbol:  st.Symbol,
			Value:   v,
			Unit:    unit,
			Rain1h:  st.Precipitation1h,
			WindKmh: st.WindSpeed,
		})
		if v != nil {
			pts = append(pts, seriesPoint{TimeUTC: st.TimeUTC.UTC().Format(time.RFC3339), Value: *v})
		}
	}

	page, pageSize := parsePageParams(r, 10)
	total := len(allRows)
	start := (page - 1) * pageSize
	if start > total {
		start = total
	}
	end := start + pageSize
	if end > total {
		end = total
	}

	locName := "Forecast Target Point"
	tz := "UTC"
	var elev *float64
	if bundle.MetNorway.Location != nil {
		if bundle.MetNorway.Location.Name != "" {
			locName = bundle.MetNorway.Location.Name
		}
		if bundle.MetNorway.Location.TimeZone != "" {
			tz = bundle.MetNorway.Location.TimeZone
		}
		elev = bundle.MetNorway.Location.Elevation
	}

	var currentStep *domain.ForecastStep
	if len(steps) > 0 {
		idx := bundle.MetNorway.CurrentStepIndex
		if idx < 0 || idx >= len(steps) {
			idx = 0
		}
		cCopy := steps[idx]
		currentStep = &cCopy
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"namespace": "tbsgagtech",
		"token":     token,
		"ui_url":    "/tbsgagtech/v1/modules/forecast/" + token,
		"embed_url": "/tbsgagtech/v1/modules/forecast/" + token + "?embed=1",
		"current":   currentStep,
		"location": map[string]any{
			"name":      locName,
			"latitude":  lat,
			"longitude": lon,
			"elevation": elev,
			"time_zone": tz,
		},
		"table": map[string]any{"page": page, "page_size": pageSize, "total": total, "rows": allRows[start:end]},
		"chart": map[string]any{"metric": metric, "unit": unit, "chart_type": chartType, "points": pts},
	})
}
