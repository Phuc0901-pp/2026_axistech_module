package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
)

// Config holds ISO 27001 compliant runtime configuration for the Go ERP platform.
type Config struct {
	Port            int
	BridgeBaseURL   string
	BridgeAPIKey    string
	ERPAPIKey       string
	EncryptionKey   string
	RequireAPIKey   bool
	RateLimitRPM    int
	SyncIntervalSec int
	DataFilePath    string
	LogLevel        string
}

// LoadFromEnv loads configuration from environment variables with safe defaults.
func LoadFromEnv() (Config, error) {
	cfg := Config{
		Port:            8080,
		BridgeBaseURL:   "http://127.0.0.1:8001",
		BridgeAPIKey:    "dev-bridge-api-key-change-me",
		ERPAPIKey:       "dev-erp-api-key-change-me",
		EncryptionKey:   "",
		RequireAPIKey:   false,
		RateLimitRPM:    300,
		SyncIntervalSec: 10,
		DataFilePath:    "",
		LogLevel:        "INFO",
	}

	if v := strings.TrimSpace(os.Getenv("ERP_PORT")); v != "" {
		p, err := strconv.Atoi(v)
		if err != nil {
			return Config{}, fmt.Errorf("invalid ERP_PORT %q: %w", v, err)
		}
		cfg.Port = p
	}
	if v := strings.TrimSpace(os.Getenv("BRIDGE_BASE_URL")); v != "" {
		cfg.BridgeBaseURL = strings.TrimRight(v, "/")
	}
	if v := strings.TrimSpace(os.Getenv("BRIDGE_API_KEY")); v != "" {
		cfg.BridgeAPIKey = v
	}
	if v := strings.TrimSpace(os.Getenv("ERP_API_KEY")); v != "" {
		cfg.ERPAPIKey = v
	}
	if v := strings.TrimSpace(os.Getenv("ERP_ENCRYPTION_KEY")); v != "" {
		cfg.EncryptionKey = v
	}
	if v := strings.TrimSpace(os.Getenv("ERP_REQUIRE_API_KEY")); v != "" {
		cfg.RequireAPIKey = strings.EqualFold(v, "true") || v == "1"
	}
	if v := strings.TrimSpace(os.Getenv("ERP_RATE_LIMIT_RPM")); v != "" {
		r, err := strconv.Atoi(v)
		if err != nil {
			return Config{}, fmt.Errorf("invalid ERP_RATE_LIMIT_RPM %q: %w", v, err)
		}
		cfg.RateLimitRPM = r
	}
	if v := strings.TrimSpace(os.Getenv("SYNC_INTERVAL_SEC")); v != "" {
		s, err := strconv.Atoi(v)
		if err != nil {
			return Config{}, fmt.Errorf("invalid SYNC_INTERVAL_SEC %q: %w", v, err)
		}
		cfg.SyncIntervalSec = s
	}
	if v := strings.TrimSpace(os.Getenv("ERP_DATA_FILE_PATH")); v != "" {
		cfg.DataFilePath = v
	} else if v := strings.TrimSpace(os.Getenv("DATA_FILE_PATH")); v != "" {
		cfg.DataFilePath = v
	}
	if v := strings.TrimSpace(os.Getenv("LOG_LEVEL")); v != "" {
		cfg.LogLevel = strings.ToUpper(v)
	}

	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

// Validate checks bounds and required URL formats.
func (c Config) Validate() error {
	if c.Port < 1 || c.Port > 65535 {
		return fmt.Errorf("port %d out of range [1, 65535]", c.Port)
	}
	u, err := url.Parse(c.BridgeBaseURL)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return fmt.Errorf("invalid BRIDGE_BASE_URL %q", c.BridgeBaseURL)
	}
	if c.SyncIntervalSec < 1 || c.SyncIntervalSec > 3600 {
		return fmt.Errorf("sync_interval_sec %d out of range [1, 3600]", c.SyncIntervalSec)
	}
	if c.RateLimitRPM < 1 || c.RateLimitRPM > 100000 {
		return fmt.Errorf("rate_limit_rpm %d out of range [1, 100000]", c.RateLimitRPM)
	}
	if strings.TrimSpace(c.BridgeAPIKey) == "" {
		return fmt.Errorf("BRIDGE_API_KEY must not be empty")
	}
	return nil
}

// String implements fmt.Stringer while masking secret API keys.
func (c Config) String() string {
	return fmt.Sprintf(
		"Config{Port:%d, BridgeBaseURL:%q, BridgeAPIKey:[REDACTED], ERPAPIKey:[REDACTED], EncryptionKey:[REDACTED], RequireAPIKey:%v, RateLimitRPM:%d, SyncIntervalSec:%d, DataFilePath:%q, LogLevel:%q}",
		c.Port, c.BridgeBaseURL, c.RequireAPIKey, c.RateLimitRPM, c.SyncIntervalSec, c.DataFilePath, c.LogLevel,
	)
}
