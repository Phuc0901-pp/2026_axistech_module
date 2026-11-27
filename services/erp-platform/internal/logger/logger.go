package logger

import (
	"io"
	"log/slog"
	"os"
	"strings"
)

const RedactedValue = "[REDACTED]"

var sensitiveFragments = []string{
	"password",
	"passwd",
	"secret",
	"token",
	"cookie",
	"authorization",
	"api_key",
	"apikey",
	"x-api-key",
}

func isSensitiveKey(key string) bool {
	lower := strings.ToLower(strings.TrimSpace(key))
	for _, frag := range sensitiveFragments {
		if strings.Contains(lower, frag) {
			return true
		}
	}
	return false
}

// NewJSONLogger builds an ISO 27001 structured JSON slog.Logger that automatically redacts secrets.
func NewJSONLogger(w io.Writer, levelStr string) *slog.Logger {
	if w == nil {
		w = os.Stdout
	}
	level := slog.LevelInfo
	switch strings.ToUpper(strings.TrimSpace(levelStr)) {
	case "DEBUG":
		level = slog.LevelDebug
	case "WARN", "WARNING":
		level = slog.LevelWarn
	case "ERROR":
		level = slog.LevelError
	}

	opts := &slog.HandlerOptions{
		Level: level,
		ReplaceAttr: func(_ []string, a slog.Attr) slog.Attr {
			if isSensitiveKey(a.Key) {
				return slog.String(a.Key, RedactedValue)
			}
			return a
		},
	}
	return slog.New(slog.NewJSONHandler(w, opts))
}
