package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
	"github.com/tanbaocorp/axisstream-erp/internal/security"
)

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (h *Handler) PostAuthLogin(w http.ResponseWriter, r *http.Request) {
	var req loginRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192)).Decode(&req); err != nil {
		WriteProblemJSON(w, http.StatusBadRequest, "INVALID_JSON", "Invalid login payload", GetCorrelationID(r.Context()))
		return
	}
	user, triesLeft, ok := h.auth.Authenticate(r.Context(), req.Email, req.Password)
	cid := GetCorrelationID(r.Context())
	if !ok {
		h.store.AppendAudit(domain.AuditEntry{
			ID:            "aud-" + generateID()[:12],
			TimestampUTC:  time.Now().UTC(),
			Actor:         strings.TrimSpace(req.Email),
			Action:        "AUTH_LOGIN_FAILED",
			ResourceType:  "session",
			ResourceID:    strings.TrimSpace(req.Email),
			CorrelationID: cid,
			Details:       "Invalid credentials",
		})
		writeJSON(w, http.StatusUnauthorized, map[string]any{
			"ok":         false,
			"tries_left": triesLeft,
			"error":      "INVALID_CREDENTIALS",
		})
		return
	}

	token, err := h.auth.SignSession(user, 24*time.Hour)
	if err != nil {
		WriteProblemJSON(w, http.StatusInternalServerError, "SESSION_SIGN_ERROR", "Unable to issue session token", cid)
		return
	}
	http.SetCookie(w, &http.Cookie{
		Name:     security.SessionCookieName,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   86400,
	})
	h.store.AppendAudit(domain.AuditEntry{
		ID:            "aud-" + generateID()[:12],
		TimestampUTC:  time.Now().UTC(),
		Actor:         user.Email,
		Action:        "AUTH_LOGIN_SUCCESS",
		ResourceType:  "session",
		ResourceID:    user.ID,
		CorrelationID: cid,
		Details:       "Role: " + user.Role,
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"ok":           true,
		"user":         user,
		"redirect_url": "/tbsgagtech/v1/overview",
	})
}

func (h *Handler) PostAuthLogout(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{
		Name:     security.SessionCookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
	h.store.AppendAudit(domain.AuditEntry{
		ID:            "aud-" + generateID()[:12],
		TimestampUTC:  time.Now().UTC(),
		Actor:         "session-user",
		Action:        "AUTH_LOGOUT",
		ResourceType:  "session",
		ResourceID:    security.SessionCookieName,
		CorrelationID: GetCorrelationID(r.Context()),
		Details:       "User signed out cleanly",
	})
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (h *Handler) GetAuthMe(w http.ResponseWriter, r *http.Request) {
	cookie, err := r.Cookie(security.SessionCookieName)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"authenticated": false})
		return
	}
	claims, ok := h.auth.VerifySession(cookie.Value)
	if !ok {
		writeJSON(w, http.StatusOK, map[string]any{"authenticated": false})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"authenticated": true,
		"user": map[string]any{
			"id":           claims.UserID,
			"email":        claims.Email,
			"display_name": claims.DisplayName,
			"role":         claims.Role,
		},
	})
}
