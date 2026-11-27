package repository

import (
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
)

func TestGUT010_TelemetryDeduplication(t *testing.T) {
	store, err := NewStore("")
	if err != nil {
		t.Fatal(err)
	}
	v := 29.5
	ts := time.Date(2026, 11, 26, 7, 0, 0, 0, time.UTC)
	snap := []domain.DeviceSnapshot{{
		DeviceID: "d1",
		Status:   "LIVE",
		Readings: []domain.TelemetryReading{{
			DeviceID: "d1", Metric: "temperature", Value: &v, Unit: "°C", TimestampUTC: ts,
		}},
	}}
	n1 := store.SaveProjectData("p1", nil, snap, nil, nil, nil, nil, nil, nil, nil)
	n2 := store.SaveProjectData("p1", nil, snap, nil, nil, nil, nil, nil, nil, nil)
	if n1 != 1 || n2 != 0 {
		t.Fatalf("expected first insert 1 and duplicate 0, got %d and %d", n1, n2)
	}
	if len(store.GetReadings("p1", "d1")) != 1 {
		t.Fatal("expected exactly 1 deduplicated reading")
	}
}

func TestGUT011_ThreadSafeConcurrentReadWrite(t *testing.T) {
	store, _ := NewStore("")
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(2)
		go func(idx int) {
			defer wg.Done()
			store.SaveProjects([]domain.Project{{ID: "p1", Name: "Proj"}})
			store.AppendAudit(domain.AuditEntry{ID: string(rune('a' + idx)), Action: "TEST"})
		}(i)
		go func() {
			defer wg.Done()
			_ = store.GetProjects()
			_ = store.ListAudit(10)
		}()
	}
	wg.Wait()
}

func TestGUT012_IncidentUpsertPreservesOperatorStatus(t *testing.T) {
	store, _ := NewStore("")
	pols := []domain.AlertPolicy{{
		ID: "pol-1", ProjectID: "p1", Name: "Wind", EntityID: "d1",
		DeviceName: "Station", Status: "ACTIVE", Priority: "HIGH", MessageTemplate: "Msg 1",
	}}
	store.SaveProjectData("p1", nil, nil, nil, nil, pols, nil, nil, nil, nil)

	inc, ok := store.GetIncident("inc-pol-1")
	if !ok || inc.Status != domain.IncidentOpen {
		t.Fatalf("expected OPEN incident, got %+v", inc)
	}
	inc.Status = domain.IncidentAcknowledged
	_ = store.UpdateIncident(inc)

	// Re-sync same active policy; status must stay ACKNOWLEDGED
	store.SaveProjectData("p1", nil, nil, nil, nil, pols, nil, nil, nil, nil)
	after, _ := store.GetIncident("inc-pol-1")
	if after.Status != domain.IncidentAcknowledged {
		t.Fatalf("expected ACKNOWLEDGED preserved, got %s", after.Status)
	}
}

func TestGUT013_AuditLogOrderAndImmutability(t *testing.T) {
	store, _ := NewStore("")
	store.AppendAudit(domain.AuditEntry{ID: "1", Action: "FIRST"})
	store.AppendAudit(domain.AuditEntry{ID: "2", Action: "SECOND"})
	entries := store.ListAudit(10)
	if len(entries) != 2 || entries[0].Action != "SECOND" || entries[1].Action != "FIRST" {
		t.Fatalf("unexpected audit order: %+v", entries)
	}
}

func TestGUT014_AtomicFilePersistenceAcrossRestart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "erp_state.json")
	s1, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	s1.SaveProjects([]domain.Project{{ID: "p-persist", Name: "TANBAOCORP_Demo"}})
	s1.AppendAudit(domain.AuditEntry{ID: "aud-1", Action: "PERSIST_CHECK"})

	s2, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(s2.GetProjects()) != 1 || s2.GetProjects()[0].ID != "p-persist" {
		t.Fatalf("projects did not survive reload: %+v", s2.GetProjects())
	}
	if len(s2.ListAudit(5)) != 1 {
		t.Fatal("audit log did not survive reload")
	}
}

func TestGUT030_ForecastPersistenceAcrossRestart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "erp_forecast_state.json")
	s1, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	s1.SaveForecast("p1", &domain.ProjectForecastBundle{
		ProjectID: "p1",
		MetNorway: domain.WeatherForecastReport{
			Provider: "MET Norway",
			Status:   "CONNECTED",
			Days:     []domain.ForecastDay{{Date: "2026-11-26"}},
		},
	})

	s2, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	got := s2.GetForecast("p1")
	if got == nil || got.MetNorway.Status != "CONNECTED" || len(got.MetNorway.Days) != 1 {
		t.Fatalf("forecast did not survive reload: %+v", got)
	}
}
