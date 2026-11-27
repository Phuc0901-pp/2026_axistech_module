package bridgeclient

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
)

func TestGUT006_SendsAPIKeyAndCorrelationID(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Key") != "bridge-key-1" {
			t.Fatalf("missing or wrong X-API-Key: %q", r.Header.Get("X-API-Key"))
		}
		if r.Header.Get("X-Correlation-ID") != "cid-99" {
			t.Fatalf("missing X-Correlation-ID: %q", r.Header.Get("X-Correlation-ID"))
		}
		_, _ = w.Write([]byte(`{"data":[{"id":"p1","name":"TANBAOCORP_Demo"}]}`))
	}))
	defer srv.Close()

	client := New(srv.URL, "bridge-key-1")
	projects, err := client.FetchProjects(context.Background(), "cid-99")
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(projects) != 1 || projects[0].Name != "TANBAOCORP_Demo" {
		t.Fatalf("unexpected projects: %+v", projects)
	}
}

func TestGUT007_RetriesTransient503AndRecovers(t *testing.T) {
	var attempts atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := attempts.Add(1)
		if n < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer srv.Close()

	client := New(srv.URL, "k", WithRetries(3, 5*time.Millisecond))
	_, err := client.FetchProjects(context.Background(), "cid-retry")
	if err != nil {
		t.Fatalf("expected retry recovery, got %v", err)
	}
	if attempts.Load() != 3 {
		t.Fatalf("expected 3 attempts, got %d", attempts.Load())
	}
}

func TestGUT008_NoRetryOn404AndCircuitBreakerTripsOn5xx(t *testing.T) {
	var count404 atomic.Int32
	srv404 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		count404.Add(1)
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv404.Close()

	client404 := New(srv404.URL, "k", WithRetries(3, 1*time.Millisecond))
	_, err := client404.FetchProjects(context.Background(), "cid")
	if !errors.Is(err, domain.ErrValidation) {
		t.Fatalf("expected ErrValidation on 404, got %v", err)
	}
	if count404.Load() != 1 {
		t.Fatalf("expected zero retries on 404, got %d calls", count404.Load())
	}

	var count500 atomic.Int32
	srv500 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		count500.Add(1)
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv500.Close()

	clientCB := New(srv500.URL, "k", WithRetries(0, 1*time.Millisecond), WithCircuitBreaker(2, 5*time.Second))
	_, _ = clientCB.FetchProjects(context.Background(), "cid1")
	_, _ = clientCB.FetchProjects(context.Background(), "cid2")
	_, err = clientCB.FetchProjects(context.Background(), "cid3")
	if !errors.Is(err, domain.ErrUpstream) {
		t.Fatalf("expected ErrUpstream from open circuit breaker, got %v", err)
	}
	if count500.Load() != 2 {
		t.Fatalf("expected circuit breaker to block 3rd call, got %d", count500.Load())
	}
}

func TestGUT009_SubscribeStreamParsesSSEFrames(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = fmt.Fprint(w, "event: telemetry_update\ndata: {\"project_id\":\"p1\"}\n\n")
	}))
	defer srv.Close()

	client := New(srv.URL, "k")
	var got []BridgeSSEEvent
	_ = client.SubscribeStream(context.Background(), func(ev BridgeSSEEvent) {
		got = append(got, ev)
	})
	if len(got) != 1 || got[0].EventType != "telemetry_update" {
		t.Fatalf("expected 1 telemetry_update SSE event, got %+v", got)
	}
}

func TestGUT029_FetchWeatherForecastParsesBundle(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/projects/p1/forecast" {
			t.Fatalf("unexpected path %s", r.URL.Path)
		}
		_, _ = w.Write([]byte(`{"project_id":"p1","met_norway":{"provider":"MET Norway","status":"CONNECTED","days":[{"date":"2026-11-26","temperature_min":24,"temperature_max":32}]},"janes_weather":{"provider":"Jane's Weather","status":"DISCONNECTED"}}`))
	}))
	defer srv.Close()

	client := New(srv.URL, "k")
	bundle, err := client.FetchWeatherForecast(context.Background(), "p1", "cid-fc")
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if bundle.MetNorway.Status != "CONNECTED" || len(bundle.MetNorway.Days) != 1 || bundle.JanesWeather.Status != "DISCONNECTED" {
		t.Fatalf("unexpected forecast bundle: %+v", bundle)
	}
}

func TestGUT043_BridgeClientFetchTelemetryHistory(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/projects/p1/telemetry/history" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("hours") != "24" || r.URL.Query().Get("device_id") != "d1" {
			t.Fatalf("unexpected query params: %s", r.URL.RawQuery)
		}
		_, _ = w.Write([]byte(`{"data":[{"device_id":"d1","external_id":"79DAAFB4","source_code":"weather","metric":"temperature","value":29.4,"unit":"°C","timestamp_utc":"2026-11-26T07:00:00Z"}],"count":1}`))
	}))
	defer srv.Close()

	client := New(srv.URL, "k")
	rows, err := client.FetchTelemetryHistory(context.Background(), "p1", "d1", 24, "cid-hist")
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(rows) != 1 || rows[0].Metric != "temperature" || rows[0].Value == nil || *rows[0].Value != 29.4 {
		t.Fatalf("unexpected telemetry history rows: %+v", rows)
	}
}
