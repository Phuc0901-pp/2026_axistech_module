package service

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/bridgeclient"
	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/logger"
	"github.com/tanbaocorp/axisstream-erp/internal/realtime"
	"github.com/tanbaocorp/axisstream-erp/internal/repository"
)

type stubBridge struct {
	failProjID string
}

func (s *stubBridge) FetchProjects(_ context.Context, _ string) ([]domain.Project, error) {
	return []domain.Project{
		{ID: "p1", Name: "TANBAOCORP_Demo", Organisation: domain.Organisation{SchemaName: "tbncorp"}},
		{ID: "p2", Name: "TBSG", Organisation: domain.Organisation{SchemaName: "tbncorp"}},
	}, nil
}

func (s *stubBridge) FetchDevices(_ context.Context, pid, _ string) ([]domain.Device, error) {
	if pid == s.failProjID {
		return nil, errors.New("partial device failure")
	}
	if pid == "p1" {
		return []domain.Device{
			{ID: "d1", ExternalID: "79DAAFB4", SourceCode: "weather", Active: true},
			{ID: "d2", ExternalID: "20001DC4", SourceCode: "waterlevel", Active: true},
		}, nil
	}
	return nil, nil
}

func (s *stubBridge) FetchTelemetry(_ context.Context, pid, _ string) ([]domain.DeviceSnapshot, error) {
	if pid != "p1" {
		return nil, nil
	}
	temp := 30.2
	return []domain.DeviceSnapshot{
		{
			DeviceID: "d1", ExternalID: "79DAAFB4", SourceCode: "weather", Status: "LIVE",
			Readings: []domain.TelemetryReading{{DeviceID: "d1", Metric: "temperature", Value: &temp, Unit: "°C", TimestampUTC: time.Now().UTC()}},
		},
		{DeviceID: "d2", ExternalID: "20001DC4", SourceCode: "waterlevel", Status: "NO_DATA"},
	}, nil
}

func (s *stubBridge) FetchFields(_ context.Context, _ string, _ string) ([]domain.FieldLocation, error) {
	return []domain.FieldLocation{{ID: "f1", Name: "TRUONG TON FARM"}}, nil
}

func (s *stubBridge) FetchAssets(_ context.Context, _ string, _ string) ([]domain.EquipmentAsset, error) {
	return []domain.EquipmentAsset{{ID: "a1", Name: "Nước", AssetType: "Water Tank"}}, nil
}

func (s *stubBridge) FetchAlertPolicies(_ context.Context, pid, _ string) ([]domain.AlertPolicy, error) {
	if pid != "p1" {
		return nil, nil
	}
	return []domain.AlertPolicy{{ID: "pol1", ProjectID: "p1", Name: "Wind", Status: "ACTIVE", Priority: "HIGH"}}, nil
}

func (s *stubBridge) FetchAlertHistory(_ context.Context, _ string, _ string) ([]domain.AlertHistoryItem, error) {
	return nil, nil
}

func (s *stubBridge) FetchProviders(_ context.Context, _ string, _ string) ([]domain.ProviderConnection, error) {
	return nil, nil
}

func (s *stubBridge) FetchWeatherExchange(_ context.Context, pid, _ string) ([]domain.ExchangeTokenInfo, []domain.WeatherExchangeRow, error) {
	if pid != "p1" {
		return nil, nil, nil
	}
	t := 29.8
	return []domain.ExchangeTokenInfo{{TokenID: "t1", Name: "TBSG"}}, []domain.WeatherExchangeRow{{
		Code: "79DAAFB4", Time: time.Date(2026, 11, 26, 7, 0, 0, 0, time.UTC), TemperatureAvg: &t,
	}}, nil
}

func (s *stubBridge) FetchWeatherForecast(_ context.Context, pid, _ string) (*domain.ProjectForecastBundle, error) {
	return &domain.ProjectForecastBundle{
		ProjectID:    pid,
		MetNorway:    domain.WeatherForecastReport{Provider: "MET Norway", Status: "CONNECTED", Days: []domain.ForecastDay{{Date: "2026-11-26"}}},
		JanesWeather: domain.WeatherForecastReport{Provider: "Jane's Weather", Status: "DISCONNECTED"},
	}, nil
}

func (s *stubBridge) TriggerSync(_ context.Context, _ string) error { return nil }
func (s *stubBridge) FetchTelemetryHistory(_ context.Context, _ string, _ string, _ int, _ string) ([]domain.TelemetryReading, error) {
	return nil, nil
}
func (s *stubBridge) FetchHealthStatus(_ context.Context) (string, string, string, error) {
	return "READY", "demo", "", nil
}
func (s *stubBridge) CheckHealth(_ context.Context) (string, error) { return "READY", nil }
func (s *stubBridge) SubscribeStream(_ context.Context, _ func(bridgeclient.BridgeSSEEvent)) error {
	return nil
}

func TestGUT015_DashboardKPIAggregation(t *testing.T) {
	store, _ := repository.NewStore("")
	hub := realtime.NewHub(8)
	svc := NewERPService(store, &stubBridge{}, hub, logger.NewJSONLogger(io.Discard, "INFO"))
	if err := svc.SyncOnce(context.Background(), "cid-1"); err != nil {
		t.Fatal(err)
	}
	dash := svc.GetDashboard("p1")
	if dash.TotalDevices != 2 || dash.LiveDevices != 1 || dash.NoDataDevices != 1 {
		t.Fatalf("unexpected device counts: %+v", dash)
	}
	if dash.OpenIncidents != 1 || dash.LatestWeather["temperature"] != 30.2 {
		t.Fatalf("unexpected incident/weather summary: %+v", dash)
	}
}

func TestGUT016_IncidentAcknowledgeAndResolveFSM(t *testing.T) {
	store, _ := repository.NewStore("")
	svc := NewERPService(store, &stubBridge{}, realtime.NewHub(8), logger.NewJSONLogger(io.Discard, "INFO"))
	_ = svc.SyncOnce(context.Background(), "cid-1")

	inc, err := svc.AcknowledgeIncident("inc-pol1", "op1", "checking", "cid-2")
	if err != nil || inc.Status != domain.IncidentAcknowledged {
		t.Fatalf("ack failed: %v %+v", err, inc)
	}
	// Cannot acknowledge twice
	if _, err := svc.AcknowledgeIncident("inc-pol1", "op1", "", "cid-3"); !errors.Is(err, domain.ErrInvalidTransition) {
		t.Fatalf("expected ErrInvalidTransition on double ack, got %v", err)
	}
	res, err := svc.ResolveIncident("inc-pol1", "op1", "fixed", "cid-4")
	if err != nil || res.Status != domain.IncidentResolved {
		t.Fatalf("resolve failed: %v", err)
	}
}

func TestGUT017_WeatherCSVExport17Columns(t *testing.T) {
	store, _ := repository.NewStore("")
	svc := NewERPService(store, &stubBridge{}, realtime.NewHub(8), logger.NewJSONLogger(io.Discard, "INFO"))
	_ = svc.SyncOnce(context.Background(), "cid-1")

	csvBytes, err := svc.ExportWeatherCSV("p1")
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(csvBytes)), "\n")
	if len(lines) != 2 {
		t.Fatalf("expected 2 CSV lines, got %d", len(lines))
	}
	cols := strings.Split(lines[0], ",")
	if len(cols) != 17 {
		t.Fatalf("expected 17 columns in CSV header, got %d", len(cols))
	}
}

func TestGUT018_SyncWorkerToleratesPartialProjectFailure(t *testing.T) {
	store, _ := repository.NewStore("")
	svc := NewERPService(store, &stubBridge{failProjID: "p2"}, realtime.NewHub(8), logger.NewJSONLogger(io.Discard, "INFO"))
	if err := svc.SyncOnce(context.Background(), "cid-partial"); err != nil {
		t.Fatalf("expected partial project failure not to fail SyncOnce, got %v", err)
	}
	if len(store.GetDevices("p1")) != 2 {
		t.Fatal("expected p1 devices still synced")
	}
	if store.GetSyncStatus().LastError == "" {
		t.Fatal("expected partial error recorded in SyncStatus")
	}
}

func TestGUT019_SyncOnceBroadcastsSSEEvent(t *testing.T) {
	store, _ := repository.NewStore("")
	hub := realtime.NewHub(8)
	ch, unsub := hub.Subscribe()
	defer unsub()

	svc := NewERPService(store, &stubBridge{}, hub, logger.NewJSONLogger(io.Discard, "INFO"))
	_ = svc.SyncOnce(context.Background(), "cid-sse")

	select {
	case ev := <-ch:
		if ev.Type != "sync_update" {
			t.Fatalf("expected sync_update, got %s", ev.Type)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for SSE broadcast")
	}
}

func TestGUT031_SyncOncePopulatesForecastInDashboard(t *testing.T) {
	store, _ := repository.NewStore("")
	svc := NewERPService(store, &stubBridge{}, realtime.NewHub(8), logger.NewJSONLogger(io.Discard, "INFO"))
	if err := svc.SyncOnce(context.Background(), "cid-fc"); err != nil {
		t.Fatal(err)
	}
	dash := svc.GetDashboard("p1")
	if dash.Forecast == nil || dash.Forecast.MetNorway.Status != "CONNECTED" || len(dash.Forecast.MetNorway.Days) != 1 {
		t.Fatalf("expected forecast populated in dashboard: %+v", dash.Forecast)
	}
}
