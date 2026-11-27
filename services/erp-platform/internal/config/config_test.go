package config

import (
	"strings"
	"testing"
)

func TestGUT001_LoadFromEnvDefaultsAndOverrides(t *testing.T) {
	t.Setenv("ERP_PORT", "9090")
	t.Setenv("BRIDGE_BASE_URL", "https://bridge.internal:8443/")
	t.Setenv("BRIDGE_API_KEY", "test-bridge-key")
	t.Setenv("SYNC_INTERVAL_SEC", "20")

	cfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Port != 9090 {
		t.Fatalf("expected port 9090, got %d", cfg.Port)
	}
	if cfg.BridgeBaseURL != "https://bridge.internal:8443" {
		t.Fatalf("expected trimmed URL, got %q", cfg.BridgeBaseURL)
	}
	if cfg.SyncIntervalSec != 20 {
		t.Fatalf("expected sync interval 20, got %d", cfg.SyncIntervalSec)
	}
}

func TestGUT002_ConfigValidationRejectsBadPortAndURL(t *testing.T) {
	t.Setenv("ERP_PORT", "70000")
	if _, err := LoadFromEnv(); err == nil {
		t.Fatal("expected error for invalid port 70000")
	}

	t.Setenv("ERP_PORT", "8080")
	t.Setenv("BRIDGE_BASE_URL", "ftp://invalid")
	if _, err := LoadFromEnv(); err == nil {
		t.Fatal("expected error for invalid URL scheme")
	}
}

func TestGUT003_ConfigStringMasksSecrets(t *testing.T) {
	cfg := Config{
		Port:            8080,
		BridgeBaseURL:   "http://127.0.0.1:8001",
		BridgeAPIKey:    "SECRET_BRIDGE_KEY_XYZ",
		ERPAPIKey:       "SECRET_ERP_KEY_ABC",
		SyncIntervalSec: 10,
	}
	s := cfg.String()
	if strings.Contains(s, "SECRET_BRIDGE_KEY_XYZ") || strings.Contains(s, "SECRET_ERP_KEY_ABC") {
		t.Fatalf("Config.String() leaked secret: %s", s)
	}
	if !strings.Contains(s, "[REDACTED]") {
		t.Fatalf("expected [REDACTED] placeholder in Config.String(): %s", s)
	}
}

func TestGUT059_ConfigDatabaseURLAndSecretMasking(t *testing.T) {
	t.Setenv("ERP_DATABASE_URL", "postgresql://agtech_admin:SUPER_SECRET_DB_PASS@postgres:5432/axistech_erp")
	cfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("expected valid postgres DSN, got err: %v", err)
	}
	if cfg.DatabaseURL == "" || strings.Contains(cfg.String(), "SUPER_SECRET_DB_PASS") {
		t.Fatalf("Config.String() leaked database password or missing DSN: %s", cfg.String())
	}

	t.Setenv("ERP_DATABASE_URL", "mysql://invalid")
	if _, err := LoadFromEnv(); err == nil {
		t.Fatal("expected error for non-postgres DatabaseURL")
	}

	t.Setenv("ERP_DATABASE_URL", "")
	t.Setenv("POSTGRES_HOST", "postgres")
	t.Setenv("POSTGRES_PORT", "5432")
	t.Setenv("POSTGRES_DB", "TbsgAgtech_db")
	t.Setenv("POSTGRES_USER", "agtech_admin")
	t.Setenv("POSTGRES_PASSWORD", "Test@Pass123")
	pgCfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("expected percent-encoded postgres DSN, got err: %v", err)
	}
	if !strings.Contains(pgCfg.DatabaseURL, "Test%40Pass123@postgres:5432/TbsgAgtech_db") {
		t.Fatalf("expected percent-encoded password in DSN, got: %s", pgCfg.DatabaseURL)
	}
	if strings.Contains(pgCfg.String(), "Test@Pass123") || strings.Contains(pgCfg.String(), "Test%40Pass123") {
		t.Fatalf("Config.String() leaked assembled Postgres password: %s", pgCfg.String())
	}
}
