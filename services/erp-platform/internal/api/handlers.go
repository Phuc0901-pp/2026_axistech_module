package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/realtime"
	"github.com/tanbaocorp/axisstream-erp/internal/repository"
	"github.com/tanbaocorp/axisstream-erp/internal/service"
)

type Handler struct {
	svc   *service.ERPService
	store *repository.Store
	hub   *realtime.Hub
	log   *slog.Logger
}

func NewHandler(svc *service.ERPService, store *repository.Store, hub *realtime.Hub, log *slog.Logger) *Handler {
	return &Handler{svc: svc, store: store, hub: hub, log: log}
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
