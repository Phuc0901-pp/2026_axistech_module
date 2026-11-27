package logger

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestGUT004_JSONLoggerEmitsValidJSON(t *testing.T) {
	var buf bytes.Buffer
	log := NewJSONLogger(&buf, "INFO")
	log.Info("erp boot", "port", 8080)

	var parsed map[string]any
	if err := json.Unmarshal(buf.Bytes(), &parsed); err != nil {
		t.Fatalf("expected valid JSON log line, got error %v: %s", err, buf.String())
	}
	if parsed["msg"] != "erp boot" {
		t.Fatalf("unexpected msg: %v", parsed["msg"])
	}
}

func TestGUT005_ISO27001LoggerRedactsSensitiveKeys(t *testing.T) {
	var buf bytes.Buffer
	log := NewJSONLogger(&buf, "DEBUG")
	log.Info("auth check",
		"password", "plain-pass-999",
		"api_key", "secret-key-888",
		"cookie", "sid=secret-cookie",
		"token", "tok-777",
		"safe_field", "ok",
	)

	out := buf.String()
	for _, secret := range []string{"plain-pass-999", "secret-key-888", "secret-cookie", "tok-777"} {
		if strings.Contains(out, secret) {
			t.Fatalf("secret %q leaked into log output: %s", secret, out)
		}
	}
	if !strings.Contains(out, RedactedValue) || !strings.Contains(out, "ok") {
		t.Fatalf("expected redacted placeholder and safe field in %s", out)
	}
}
