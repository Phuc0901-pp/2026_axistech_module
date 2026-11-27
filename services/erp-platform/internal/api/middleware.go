package api

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

type ctxKey string

const correlationIDKey ctxKey = "correlation_id"

// RouterSecurityOptions configures rate limiting and optional write API key protection.
type RouterSecurityOptions struct {
	RateLimitRPM  int
	RequireAPIKey bool
	APIKey        string
}

func GetCorrelationID(ctx context.Context) string {
	if v, ok := ctx.Value(correlationIDKey).(string); ok && v != "" {
		return v
	}
	return ""
}

func generateID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func WriteProblemJSON(w http.ResponseWriter, status int, title, detail, cid string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"type":           "https://errors.axisstream-erp.local/" + title,
		"title":          title,
		"status":         status,
		"detail":         detail,
		"correlation_id": cid,
	})
}

type ipRateLimiter struct {
	mu      sync.Mutex
	maxRPM  int
	windows map[string][]time.Time
}

func newIPRateLimiter(maxRPM int) *ipRateLimiter {
	if maxRPM <= 0 {
		maxRPM = 300
	}
	return &ipRateLimiter{maxRPM: maxRPM, windows: make(map[string][]time.Time)}
}

func (l *ipRateLimiter) allow(ip string) bool {
	now := time.Now()
	cutoff := now.Add(-1 * time.Minute)
	l.mu.Lock()
	defer l.mu.Unlock()
	list := l.windows[ip]
	kept := list[:0]
	for _, ts := range list {
		if ts.After(cutoff) {
			kept = append(kept, ts)
		}
	}
	if len(kept) >= l.maxRPM {
		l.windows[ip] = kept
		return false
	}
	l.windows[ip] = append(kept, now)
	return true
}

func clientIP(r *http.Request) string {
	if host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr)); err == nil && host != "" {
		return host
	}
	if r.RemoteAddr != "" {
		return r.RemoteAddr
	}
	return "127.0.0.1"
}

// SecurityAndCorrelationMiddleware enforces ISO 27001 headers, sliding-window rate limiting, optional API-key guard on mutations, and panic recovery.
func SecurityAndCorrelationMiddleware(log *slog.Logger, next http.Handler, opts ...RouterSecurityOptions) http.Handler {
	var cfg RouterSecurityOptions
	if len(opts) > 0 {
		cfg = opts[0]
	}
	limiter := newIPRateLimiter(cfg.RateLimitRPM)

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cid := r.Header.Get("X-Correlation-ID")
		if cid == "" {
			cid = generateID()
		}
		ctx := context.WithValue(r.Context(), correlationIDKey, cid)
		r = r.WithContext(ctx)

		w.Header().Set("X-Correlation-ID", cid)
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		w.Header().Set("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data: blob: https://mt0.google.com https://mt1.google.com https://mt2.google.com https://mt3.google.com https://*.googleapis.com https://*.gstatic.com; connect-src 'self'; font-src 'self' data:")

		defer func() {
			if rec := recover(); rec != nil {
				log.Error("HTTP handler panic recovered", "correlation_id", cid, "panic", rec)
				WriteProblemJSON(w, http.StatusInternalServerError, "INTERNAL_SERVER_ERROR", "Internal server error", cid)
			}
		}()

		if strings.HasPrefix(r.URL.Path, "/api/") {
			if !limiter.allow(clientIP(r)) {
				w.Header().Set("Retry-After", "60")
				WriteProblemJSON(w, http.StatusTooManyRequests, "RATE_LIMIT_EXCEEDED", "API rate limit exceeded", cid)
				return
			}
			if cfg.RequireAPIKey && r.Method == http.MethodPost {
				provided := strings.TrimSpace(r.Header.Get("X-API-Key"))
				expected := strings.TrimSpace(cfg.APIKey)
				if expected == "" || len(provided) != len(expected) || subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) != 1 {
					WriteProblemJSON(w, http.StatusUnauthorized, "UNAUTHORIZED", "Missing or invalid X-API-Key header for state mutation", cid)
					return
				}
			}
		}

		next.ServeHTTP(w, r)
	})
}
