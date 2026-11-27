package api

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tanbaocorp/axisstream-erp/internal/bridgeclient"
	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/logger"
	"github.com/tanbaocorp/axisstream-erp/internal/realtime"
	"github.com/tanbaocorp/axisstream-erp/internal/repository"
	"github.com/tanbaocorp/axisstream-erp/internal/service"
)

type apiTestBridge struct{}

func (a *apiTestBridge) FetchProjects(_ context.Context, _ string) ([]domain.Project, error) {
	return []domain.Project{{ID: "p1", Name: "TANBAOCORP_Demo", Organisation: domain.Organisation{SchemaName: "tbncorp"}}}, nil
}
func (a *apiTestBridge) FetchDevices(_ context.Context, _ string, _ string) ([]domain.Device, error) {
	lat, lon := 11.6901, 106.8495
	return []domain.Device{{
		ID: "d1", Name: "Weather", ExternalID: "79DAAFB4", SourceCode: "weather", Active: true,
		Coordinates: &domain.Coordinates{Latitude: lat, Longitude: lon},
	}}, nil
}
func (a *apiTestBridge) FetchTelemetry(_ context.Context, _ string, _ string) ([]domain.DeviceSnapshot, error) {
	return []domain.DeviceSnapshot{{DeviceID: "d1", ExternalID: "79DAAFB4", SourceCode: "weather", Status: "LIVE"}}, nil
}
func (a *apiTestBridge) FetchFields(_ context.Context, _ string, _ string) ([]domain.FieldLocation, error) {
	return []domain.FieldLocation{{ID: "f1", Name: "TRUONG TON FARM"}}, nil
}
func (a *apiTestBridge) FetchAssets(_ context.Context, _ string, _ string) ([]domain.EquipmentAsset, error) {
	return []domain.EquipmentAsset{{ID: "a1", Name: "Nước", AssetType: "Water Tank"}}, nil
}
func (a *apiTestBridge) FetchAlertPolicies(_ context.Context, _ string, _ string) ([]domain.AlertPolicy, error) {
	return []domain.AlertPolicy{{ID: "pol1", ProjectID: "p1", Name: "High Wind", Status: "ACTIVE", Priority: "HIGH"}}, nil
}
func (a *apiTestBridge) FetchAlertHistory(_ context.Context, _ string, _ string) ([]domain.AlertHistoryItem, error) {
	return nil, nil
}
func (a *apiTestBridge) FetchProviders(_ context.Context, _ string, _ string) ([]domain.ProviderConnection, error) {
	return nil, nil
}
func (a *apiTestBridge) FetchWeatherExchange(_ context.Context, _ string, _ string) ([]domain.ExchangeTokenInfo, []domain.WeatherExchangeRow, error) {
	return nil, nil, nil
}
func (a *apiTestBridge) FetchWeatherForecast(_ context.Context, pid string, _ string) (*domain.ProjectForecastBundle, error) {
	lat, lon := 11.6901, 106.8495
	return &domain.ProjectForecastBundle{
		ProjectID: pid,
		MetNorway: domain.WeatherForecastReport{
			Provider: "MET Norway",
			Status:   "CONNECTED",
			Location: &domain.ForecastLocation{Name: "Long Tân", Latitude: &lat, Longitude: &lon, TimeZone: "Asia/Phnom_Penh"},
			Days:     []domain.ForecastDay{{Date: "2026-11-26"}},
		},
		JanesWeather: domain.WeatherForecastReport{Provider: "Jane's Weather", Status: "DISCONNECTED"},
	}, nil
}
func (a *apiTestBridge) TriggerSync(_ context.Context, _ string) error { return nil }
func (a *apiTestBridge) FetchTelemetryHistory(_ context.Context, _ string, did string, _ int, _ string) ([]domain.TelemetryReading, error) {
	v := 29.4
	if did == "" {
		did = "d1"
	}
	return []domain.TelemetryReading{{DeviceID: did, ExternalID: "79DAAFB4", SourceCode: "weather", Metric: "temperature", Value: &v, Unit: "°C"}}, nil
}
func (a *apiTestBridge) FetchHealthStatus(_ context.Context) (string, string, string, error) {
	return "READY", "demo", "", nil
}
func (a *apiTestBridge) CheckHealth(_ context.Context) (string, error) { return "READY", nil }
func (a *apiTestBridge) SubscribeStream(_ context.Context, _ func(bridgeclient.BridgeSSEEvent)) error {
	return nil
}

func setupTestRouter(t *testing.T) (http.Handler, *repository.Store) {
	t.Helper()
	store, _ := repository.NewStore("")
	hub := realtime.NewHub(16)
	log := logger.NewJSONLogger(io.Discard, "INFO")
	svc := service.NewERPService(store, &apiTestBridge{}, hub, log)
	if err := svc.SyncOnce(context.Background(), "test-init"); err != nil {
		t.Fatal(err)
	}
	return NewRouter(NewHandler(svc, store, hub, log), log), store
}

func TestGUT023_ERPQueryEndpoints(t *testing.T) {
	router, _ := setupTestRouter(t)
	for _, ep := range []string{
		"/api/erp/v1/dashboard",
		"/api/erp/v1/projects",
		"/api/erp/v1/devices",
		"/api/erp/v1/telemetry",
		"/api/erp/v1/fields",
		"/api/erp/v1/assets",
		"/api/erp/v1/alerts/policies",
		"/api/erp/v1/exchange/weather",
		"/api/erp/v1/audit",
	} {
		req := httptest.NewRequest(http.MethodGet, ep, nil)
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("GET %s expected 200, got %d", ep, rec.Code)
		}
	}
}

func TestGUT024_IncidentWorkflowAPIAndAuditTrail(t *testing.T) {
	router, store := setupTestRouter(t)
	beforeAudit := len(store.ListAudit(100))

	reqAck := httptest.NewRequest(http.MethodPost, "/api/erp/v1/incidents/inc-pol1/acknowledge", bytes.NewBufferString(`{"actor":"admin","notes":"on it"}`))
	recAck := httptest.NewRecorder()
	router.ServeHTTP(recAck, reqAck)
	if recAck.Code != http.StatusOK {
		t.Fatalf("ack expected 200, got %d: %s", recAck.Code, recAck.Body.String())
	}

	reqRes := httptest.NewRequest(http.MethodPost, "/api/erp/v1/incidents/inc-pol1/resolve", bytes.NewBufferString(`{"actor":"admin","notes":"done"}`))
	recRes := httptest.NewRecorder()
	router.ServeHTTP(recRes, reqRes)
	if recRes.Code != http.StatusOK {
		t.Fatalf("resolve expected 200, got %d", recRes.Code)
	}

	if len(store.ListAudit(100)) != beforeAudit+2 {
		t.Fatal("expected 2 audit entries recorded for ack+resolve")
	}
}

func TestGUT025_ISO27001SecurityHeadersEnforced(t *testing.T) {
	router, _ := setupTestRouter(t)
	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("X-Correlation-ID", "cid-sec-check")
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Header().Get("X-Frame-Options") != "DENY" ||
		rec.Header().Get("X-Content-Type-Options") != "nosniff" ||
		rec.Header().Get("X-Correlation-ID") != "cid-sec-check" {
		t.Fatalf("missing security headers: %+v", rec.Header())
	}
}

func TestGUT026_RFC9457ErrorOnInvalidIncidentTransition(t *testing.T) {
	router, _ := setupTestRouter(t)
	req := httptest.NewRequest(http.MethodPost, "/api/erp/v1/incidents/nonexistent/acknowledge", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
	if !strings.HasPrefix(rec.Header().Get("Content-Type"), "application/problem+json") {
		t.Fatalf("expected application/problem+json, got %q", rec.Header().Get("Content-Type"))
	}
	var prob map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &prob)
	if prob["title"] != "INCIDENT_NOT_FOUND" {
		t.Fatalf("unexpected problem title: %+v", prob)
	}
}

func TestGUT027_EmbeddedISODashboardStaticAssets(t *testing.T) {
	router, _ := setupTestRouter(t)
	for _, path := range []string{"/", "/css/app.css", "/js/app.js"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK || rec.Body.Len() == 0 {
			t.Fatalf("static %s expected 200 non-empty, got %d", path, rec.Code)
		}
	}
}

func TestGUT028_HealthLiveAndReadyProbes(t *testing.T) {
	router, store := setupTestRouter(t)
	recLive := httptest.NewRecorder()
	router.ServeHTTP(recLive, httptest.NewRequest(http.MethodGet, "/health/live", nil))
	if recLive.Code != http.StatusOK {
		t.Fatalf("/health/live expected 200, got %d", recLive.Code)
	}

	recReady := httptest.NewRecorder()
	router.ServeHTTP(recReady, httptest.NewRequest(http.MethodGet, "/health/ready", nil))
	if recReady.Code != http.StatusOK {
		t.Fatalf("/health/ready expected 200, got %d", recReady.Code)
	}

	store.SetSyncStatus(domain.SyncStatus{BridgeHealth: "DOWN"})
	recDown := httptest.NewRecorder()
	router.ServeHTTP(recDown, httptest.NewRequest(http.MethodGet, "/health/ready", nil))
	if recDown.Code != http.StatusServiceUnavailable {
		t.Fatalf("/health/ready expected 503 when bridge DOWN, got %d", recDown.Code)
	}
}

func TestGUT032_ForecastEndpointAndEmbeddedUITab(t *testing.T) {
	router, _ := setupTestRouter(t)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/erp/v1/forecast?project_id=p1", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("/api/erp/v1/forecast expected 200, got %d", rec.Code)
	}
	var bundle domain.ProjectForecastBundle
	if err := json.Unmarshal(rec.Body.Bytes(), &bundle); err != nil {
		t.Fatal(err)
	}
	if bundle.MetNorway.Status != "CONNECTED" || bundle.JanesWeather.Status != "DISCONNECTED" {
		t.Fatalf("unexpected forecast bundle: %+v", bundle)
	}

	uiRec := httptest.NewRecorder()
	router.ServeHTTP(uiRec, httptest.NewRequest(http.MethodGet, "/", nil))
	if !strings.Contains(uiRec.Body.String(), "tab-forecast") {
		t.Fatal("embedded index.html missing Weather Forecast tab")
	}
}

func TestGUT033_CSPAllowsGoogleSatelliteTilesAndLocksScripts(t *testing.T) {
	router, _ := setupTestRouter(t)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	csp := rec.Header().Get("Content-Security-Policy")
	for _, required := range []string{
		"script-src 'self'",
		"https://mt0.google.com",
		"https://mt3.google.com",
	} {
		if !strings.Contains(csp, required) {
			t.Fatalf("CSP missing %q: %s", required, csp)
		}
	}
	if rec.Header().Get("X-Frame-Options") != "DENY" {
		t.Fatal("missing X-Frame-Options DENY")
	}
}

func TestGUT034_EmbeddedModularFrontendAndVendorAssets(t *testing.T) {
	router, _ := setupTestRouter(t)
	assets := []string{
		"/",
		"/css/tokens.css",
		"/css/app.css",
		"/vendor/leaflet.min.css",
		"/vendor/leaflet.min.js",
		"/vendor/lucide.min.js",
		"/js/icons.js",
		"/js/map-engine.js",
		"/js/charts.js",
		"/js/inspector.js",
		"/js/app.js",
	}
	for _, p := range assets {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, p, nil))
		if rec.Code != http.StatusOK || rec.Body.Len() == 0 {
			t.Fatalf("embedded asset %s failed: status=%d len=%d", p, rec.Code, rec.Body.Len())
		}
	}
	for _, blocked := range []string{"/js/chibi-icons.js", "/init.js", "/js/init.js"} {
		removed := httptest.NewRecorder()
		router.ServeHTTP(removed, httptest.NewRequest(http.MethodGet, blocked, nil))
		if removed.Code != http.StatusNotFound {
			t.Fatalf("%s must return 404, got %d", blocked, removed.Code)
		}
	}
}

func TestGUT035_SatelliteMapDataEndpointsReturnGeoJSONAndCoords(t *testing.T) {
	router, _ := setupTestRouter(t)
	recDash := httptest.NewRecorder()
	router.ServeHTTP(recDash, httptest.NewRequest(http.MethodGet, "/api/erp/v1/dashboard?project_id=p1", nil))
	if recDash.Code != http.StatusOK || !strings.Contains(recDash.Body.String(), "79DAAFB4") {
		t.Fatalf("dashboard missing device payload: %s", recDash.Body.String())
	}

	recFields := httptest.NewRecorder()
	router.ServeHTTP(recFields, httptest.NewRequest(http.MethodGet, "/api/erp/v1/fields?project_id=p1", nil))
	if recFields.Code != http.StatusOK || !strings.Contains(recFields.Body.String(), "TRUONG TON FARM") {
		t.Fatalf("fields missing farm location payload: %s", recFields.Body.String())
	}
}

func TestGUT036_DeviceInspectorTelemetryAndAlertHistoryEndpoints(t *testing.T) {
	router, _ := setupTestRouter(t)
	recTel := httptest.NewRecorder()
	router.ServeHTTP(recTel, httptest.NewRequest(http.MethodGet, "/api/erp/v1/telemetry?project_id=p1&device_id=d1", nil))
	if recTel.Code != http.StatusOK {
		t.Fatalf("telemetry query failed: %d", recTel.Code)
	}

	recHist := httptest.NewRecorder()
	router.ServeHTTP(recHist, httptest.NewRequest(http.MethodGet, "/api/erp/v1/alerts/history?project_id=p1", nil))
	if recHist.Code != http.StatusOK {
		t.Fatalf("alert history query failed: %d", recHist.Code)
	}
}

func TestGUT037_IndexHTMLWiresSatelliteDrawerSearchAndPureLucide(t *testing.T) {
	router, _ := setupTestRouter(t)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	html := rec.Body.String()
	for _, token := range []string{
		`id="overviewMap"`,
		`id="fullMap"`,
		`id="deviceDrawer"`,
		`id="searchModal"`,
		`id="vendorGrid"`,
		`id="productList"`,
		`id="productDetailPanel"`,
		`id="productRealtimeCanvas"`,
		`/vendor/leaflet.min.js`,
		`/vendor/lucide.min.js`,
		`/js/icons.js`,
		`/js/map-engine.js`,
	} {
		if !strings.Contains(html, token) {
			t.Fatalf("index.html missing %s", token)
		}
	}
	if strings.Contains(strings.ToLower(html), "chibi") {
		t.Fatal("index.html must not contain legacy chibi icon references")
	}
}

func TestGUT040_EncryptedStorePersistenceAndSecurityStatusAPI(t *testing.T) {
	tmpFile := t.TempDir() + "/encrypted_erp_state.json"
	store, err := repository.NewEncryptedStore(tmpFile, "test-iso27001-erp-key")
	if err != nil {
		t.Fatalf("NewEncryptedStore failed: %v", err)
	}
	hub := realtime.NewHub(8)
	log := logger.NewJSONLogger(io.Discard, "INFO")
	svc := service.NewERPService(store, &apiTestBridge{}, hub, log)
	if err := svc.SyncOnce(context.Background(), "cid-enc-1"); err != nil {
		t.Fatalf("SyncOnce failed: %v", err)
	}

	reloaded, err := repository.NewEncryptedStore(tmpFile, "test-iso27001-erp-key")
	if err != nil {
		t.Fatalf("reload encrypted store failed: %v", err)
	}
	if !reloaded.EncryptionEnabled() || !reloaded.VerifyAuditChain() || reloaded.AuditCount() == 0 {
		t.Fatalf("unexpected encrypted store state: enc=%v chain=%v audits=%d",
			reloaded.EncryptionEnabled(), reloaded.VerifyAuditChain(), reloaded.AuditCount())
	}

	router := NewRouter(NewHandler(service.NewERPService(reloaded, &apiTestBridge{}, hub, log), reloaded, hub, log), log)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/erp/v1/security/status", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 on security status, got %d: %s", rec.Code, rec.Body.String())
	}
	var posture domain.SecurityPosture
	if err := json.Unmarshal(rec.Body.Bytes(), &posture); err != nil {
		t.Fatalf("invalid security status JSON: %v", err)
	}
	if !posture.EncryptionAtRest || posture.EncryptionAlgorithm != "AES-256-GCM" || !posture.AuditChainVerified || posture.AuditEntries == 0 {
		t.Fatalf("unexpected security posture: %+v", posture)
	}
	if rec.Header().Get("Strict-Transport-Security") == "" || rec.Header().Get("Permissions-Policy") == "" {
		t.Fatalf("missing HSTS or Permissions-Policy security header")
	}
}

func TestGUT041_PureLucideAxisTechEnterpriseERPWorkflow(t *testing.T) {
	router, _ := setupTestRouter(t)
	legacy1 := "xiao" + "ma"
	legacy2 := "multi_" + "vendor"
	checked := []string{"/", "/js/icons.js", "/js/map-engine.js", "/js/inspector.js", "/js/app.js", "/js/charts.js", "/css/tokens.css", "/css/app.css"}
	for _, path := range checked {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, path, nil))
		if rec.Code != http.StatusOK {
			t.Fatalf("failed fetching %s: %d", path, rec.Code)
		}
		lower := strings.ToLower(rec.Body.String())
		if strings.Contains(lower, "chibi") || strings.Contains(lower, legacy1) || strings.Contains(lower, legacy2) {
			t.Fatalf("static asset %s contains removed legacy vendor or chibi reference", path)
		}
	}

	appRec := httptest.NewRecorder()
	router.ServeHTTP(appRec, httptest.NewRequest(http.MethodGet, "/js/app.js", nil))
	appJs := appRec.Body.String()
	for _, sym := range []string{
		"renderCascadingWorkflow",
		"renderCascadingStep3",
		"getActiveWorkspaceContext",
		"renderAudit",
		"powerBadge",
		"PAGE_SIZE = 20",
		"weatherSymbolBadgeHtml",
		"ERPIcons",
	} {
		if !strings.Contains(appJs, sym) {
			t.Fatalf("app.js missing ERP workflow symbol %q", sym)
		}
	}
}

func TestGUT042_RealtimeChartsEngineAndFavicon(t *testing.T) {
	router, _ := setupTestRouter(t)
	chartRec := httptest.NewRecorder()
	router.ServeHTTP(chartRec, httptest.NewRequest(http.MethodGet, "/js/charts.js", nil))
	chartJS := chartRec.Body.String()
	if chartRec.Code != http.StatusOK || !strings.Contains(chartJS, "renderRealtimeSeries") || !strings.Contains(chartJS, "renderComponentChartsGrid") {
		t.Fatalf("charts.js missing renderRealtimeSeries or renderComponentChartsGrid export")
	}
	if !strings.Contains(chartJS, "setupCanvas(canvas") || strings.Contains(chartJS, "fitHiDpi") {
		t.Fatalf("charts.js must use setupCanvas(canvas) and never call undefined fitHiDpi")
	}

	appRec := httptest.NewRecorder()
	router.ServeHTTP(appRec, httptest.NewRequest(http.MethodGet, "/js/app.js", nil))
	if !strings.Contains(appRec.Body.String(), "buildComponentChartSpecs") {
		t.Fatal("app.js missing buildComponentChartSpecs")
	}

	favRec := httptest.NewRecorder()
	router.ServeHTTP(favRec, httptest.NewRequest(http.MethodGet, "/favicon.svg", nil))
	if favRec.Code != http.StatusOK || favRec.Body.Len() == 0 {
		t.Fatalf("favicon.svg missing: status=%d", favRec.Code)
	}

	htmlRec := httptest.NewRecorder()
	router.ServeHTTP(htmlRec, httptest.NewRequest(http.MethodGet, "/", nil))
	html := htmlRec.Body.String()
	if strings.Contains(html, `id="tab-exchange"`) || strings.Contains(html, `data-tab="exchange"`) {
		t.Fatal("index.html must not contain removed Weather Exchange tab")
	}
	for _, canvasID := range []string{
		`data-tab="api-module"`,
		`id="tab-api-module"`,
		`id="apiModuleMap"`,
		`id="apiModuleChartCanvas"`,
		`id="apiModuleTableBody"`,
		`id="apiModulePagination"`,
		`id="productRealtimeCanvas"`,
		`id="trendCanvas"`,
		`id="forecastCanvas"`,
		`id="componentChartsGrid"`,
		`id="forecastComponentCharts"`,
		`id="forecastSymbolStrip"`,
		`id="alertHistoryPagination"`,
		`id="auditPagination"`,
		`id="telemetryComponentCharts"`,
		`id="securityPostureGrid"`,
		`id="securityOverallBadge"`,
	} {
		if !strings.Contains(html, canvasID) {
			t.Fatalf("index.html missing ERP element %s", canvasID)
		}
	}
}

func TestGUT046_ApiModuleDeviceModesAnd10RowPagination(t *testing.T) {
	router, _ := setupTestRouter(t)
	htmlRec := httptest.NewRecorder()
	router.ServeHTTP(htmlRec, httptest.NewRequest(http.MethodGet, "/", nil))
	html := htmlRec.Body.String()
	for _, tok := range []string{`data-api-mode="devices"`, `data-api-mode="forecast"`, `id="apiModuleDeviceSelect"`} {
		if !strings.Contains(html, tok) {
			t.Fatalf("index.html missing API Module Device control %s", tok)
		}
	}

	appRec := httptest.NewRecorder()
	router.ServeHTTP(appRec, httptest.NewRequest(http.MethodGet, "/js/app.js", nil))
	appJs := appRec.Body.String()
	for _, sym := range []string{"API_MODULE_PAGE_SIZE = 10", "renderApiModuleDevice", "API_FORECAST_METRICS"} {
		if !strings.Contains(appJs, sym) {
			t.Fatalf("app.js missing API Module Device symbol %q", sym)
		}
	}
}

func TestGUT047_ForecastLocationMapAndWGS84Guard(t *testing.T) {
	router, _ := setupTestRouter(t)
	mapRec := httptest.NewRecorder()
	router.ServeHTTP(mapRec, httptest.NewRequest(http.MethodGet, "/js/map-engine.js", nil))
	mapJs := mapRec.Body.String()
	for _, sym := range []string{"forecastGroup", "renderForecastLocation", "lat >= -90 && lat <= 90"} {
		if !strings.Contains(mapJs, sym) {
			t.Fatalf("map-engine.js missing forecast geolocation symbol %q", sym)
		}
	}

	appRec := httptest.NewRecorder()
	router.ServeHTTP(appRec, httptest.NewRequest(http.MethodGet, "/js/app.js", nil))
	if !strings.Contains(appRec.Body.String(), "resolveForecastLocation") {
		t.Fatal("app.js missing resolveForecastLocation helper")
	}
}

func TestGUT048_ForecastLocationAndDeviceCoordsAPI(t *testing.T) {
	router, _ := setupTestRouter(t)
	fcRec := httptest.NewRecorder()
	router.ServeHTTP(fcRec, httptest.NewRequest(http.MethodGet, "/api/erp/v1/forecast?project_id=p1", nil))
	if fcRec.Code != http.StatusOK || !strings.Contains(fcRec.Body.String(), "11.6901") || !strings.Contains(fcRec.Body.String(), "106.8495") {
		t.Fatalf("forecast response missing target location coordinates: %s", fcRec.Body.String())
	}

	devRec := httptest.NewRecorder()
	router.ServeHTTP(devRec, httptest.NewRequest(http.MethodGet, "/api/erp/v1/devices?project_id=p1", nil))
	if devRec.Code != http.StatusOK || !strings.Contains(devRec.Body.String(), "11.6901") {
		t.Fatalf("devices response missing coordinates: %s", devRec.Body.String())
	}
}

func TestGUT045_RateLimiterAndRequireAPIKeyMutationGuard(t *testing.T) {
	store, _ := repository.NewStore("")
	hub := realtime.NewHub(8)
	log := logger.NewJSONLogger(io.Discard, "INFO")
	svc := service.NewERPService(store, &apiTestBridge{}, hub, log)
	router := NewRouterWithOptions(NewHandler(svc, store, hub, log), log, RouterSecurityOptions{
		RateLimitRPM:  3,
		RequireAPIKey: true,
		APIKey:        "erp-mutation-secret",
	})

	reqNoKey := httptest.NewRequest(http.MethodPost, "/api/erp/v1/sync/now", nil)
	reqNoKey.RemoteAddr = "198.51.100.10:12345"
	rec1 := httptest.NewRecorder()
	router.ServeHTTP(rec1, reqNoKey)
	if rec1.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 without API key, got %d", rec1.Code)
	}

	reqWithKey := httptest.NewRequest(http.MethodPost, "/api/erp/v1/sync/now", nil)
	reqWithKey.RemoteAddr = "198.51.100.10:12345"
	reqWithKey.Header.Set("X-API-Key", "erp-mutation-secret")
	rec2 := httptest.NewRecorder()
	router.ServeHTTP(rec2, reqWithKey)
	if rec2.Code != http.StatusOK {
		t.Fatalf("expected 200 with valid X-API-Key, got %d: %s", rec2.Code, rec2.Body.String())
	}

	reqGet := httptest.NewRequest(http.MethodGet, "/api/erp/v1/security/status", nil)
	reqGet.RemoteAddr = "198.51.100.10:12345"
	rec3 := httptest.NewRecorder()
	router.ServeHTTP(rec3, reqGet)
	if rec3.Code != http.StatusOK {
		t.Fatalf("expected 200 for 3rd request within RPM limit, got %d", rec3.Code)
	}

	reqLimited := httptest.NewRequest(http.MethodGet, "/api/erp/v1/security/status", nil)
	reqLimited.RemoteAddr = "198.51.100.10:12345"
	rec4 := httptest.NewRecorder()
	router.ServeHTTP(rec4, reqLimited)
	if rec4.Code != http.StatusTooManyRequests || rec4.Header().Get("Retry-After") == "" {
		t.Fatalf("expected 429 rate limit on 4th request, got %d", rec4.Code)
	}
}

func TestGUT044_TelemetryHistoryEndpointAndHydrationWiring(t *testing.T) {
	router, _ := setupTestRouter(t)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/erp/v1/telemetry/history?project_id=p1&device_id=d1&hours=24", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 on telemetry history endpoint, got %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"temperature"`) {
		t.Fatalf("expected temperature history reading fallback in response, got %s", rec.Body.String())
	}

	appRec := httptest.NewRecorder()
	router.ServeHTTP(appRec, httptest.NewRequest(http.MethodGet, "/js/app.js", nil))
	if !strings.Contains(appRec.Body.String(), "/api/erp/v1/telemetry/history") || !strings.Contains(appRec.Body.String(), "ingestHistoryReadings") {
		t.Fatal("app.js missing telemetry history hydration wiring")
	}
}
