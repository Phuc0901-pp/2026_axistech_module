package security

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	SessionCookieName = "axistech_session"
	defaultAdminHash  = "pbkdf2_sha256$100000$3d372b5efd2b3ee2fa4a8df323f1fe4e$9d9a3de495edab4c4107df6f1d081b276e8b227fb49ef47b5bd170bdfb9ebeec"
	maxLoginTries     = 3
)

type AuthUser struct {
	ID           string     `json:"id"`
	Email        string     `json:"email"`
	DisplayName  string     `json:"display_name"`
	Role         string     `json:"role"`
	PasswordHash string     `json:"-"`
	Active       bool       `json:"active"`
	LastLoginUTC *time.Time `json:"last_login_utc,omitempty"`
}

type SessionClaims struct {
	UserID      string `json:"uid"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
	Role        string `json:"role"`
	ExpiresUnix int64  `json:"exp"`
}

type UserLookupFn func(ctx context.Context, email string) (*AuthUser, error)
type RecordLoginFn func(ctx context.Context, email string, success bool)

type AuthManager struct {
	mu          sync.Mutex
	signingKey  []byte
	users       map[string]*AuthUser
	failedTries map[string]int
	lookupFn    UserLookupFn
	recordFn    RecordLoginFn
}

func pbkdf2SHA256(password, salt []byte, iter, keyLen int) []byte {
	prf := hmac.New(sha256.New, password)
	hashLen := sha256.Size
	numBlocks := (keyLen + hashLen - 1) / hashLen
	dk := make([]byte, 0, numBlocks*hashLen)
	u := make([]byte, hashLen)
	t := make([]byte, hashLen)
	var intBuf [4]byte

	for block := 1; block <= numBlocks; block++ {
		prf.Reset()
		prf.Write(salt)
		intBuf[0] = byte(block >> 24)
		intBuf[1] = byte(block >> 16)
		intBuf[2] = byte(block >> 8)
		intBuf[3] = byte(block)
		prf.Write(intBuf[:])
		copy(u, prf.Sum(nil))
		copy(t, u)
		for i := 2; i <= iter; i++ {
			prf.Reset()
			prf.Write(u)
			copy(u, prf.Sum(nil))
			for j := 0; j < hashLen; j++ {
				t[j] ^= u[j]
			}
		}
		dk = append(dk, t...)
	}
	return dk[:keyLen]
}

// HashPasswordPBKDF2 formats a salted PBKDF2-HMAC-SHA256 password digest.
func HashPasswordPBKDF2(password string) (string, error) {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	dk := pbkdf2SHA256([]byte(password), salt, 100000, 32)
	return fmt.Sprintf("pbkdf2_sha256$100000$%s$%s", hex.EncodeToString(salt), hex.EncodeToString(dk)), nil
}

// VerifyPasswordPBKDF2 verifies a plaintext password against a stored pbkdf2_sha256 digest in constant time.
func VerifyPasswordPBKDF2(password, storedHash string) bool {
	parts := strings.Split(strings.TrimSpace(storedHash), "$")
	if len(parts) != 4 || parts[0] != "pbkdf2_sha256" {
		return false
	}
	iter, err := strconv.Atoi(parts[1])
	if err != nil || iter < 1000 || iter > 1000000 {
		return false
	}
	salt, err := hex.DecodeString(parts[2])
	if err != nil || len(salt) == 0 {
		return false
	}
	expectedDK, err := hex.DecodeString(parts[3])
	if err != nil || len(expectedDK) == 0 {
		return false
	}
	computed := pbkdf2SHA256([]byte(password), salt, iter, len(expectedDK))
	return subtle.ConstantTimeCompare(computed, expectedDK) == 1
}

// NewAuthManager initializes ISO 27001 authentication with PBKDF2-SHA256 seeded administrator identity.
func NewAuthManager(secretMaterial string) *AuthManager {
	var key [32]byte
	if strings.TrimSpace(secretMaterial) != "" {
		key = sha256.Sum256([]byte("axistech-session-v1:" + secretMaterial))
	} else {
		_, _ = rand.Read(key[:])
	}

	adminEmail := strings.ToLower(strings.TrimSpace(os.Getenv("ERP_ADMIN_EMAIL")))
	if adminEmail == "" {
		adminEmail = "admin@tanbaocorp.vn"
	}
	adminHash := defaultAdminHash
	if envPass := strings.TrimSpace(os.Getenv("ERP_ADMIN_PASSWORD")); envPass != "" {
		if h, err := HashPasswordPBKDF2(envPass); err == nil {
			adminHash = h
		}
	}

	am := &AuthManager{
		signingKey:  key[:],
		users:       make(map[string]*AuthUser),
		failedTries: make(map[string]int),
	}
	am.users[adminEmail] = &AuthUser{
		ID:           "usr-tbsg-admin-01",
		Email:        adminEmail,
		DisplayName:  "TBSG Administrator",
		Role:         "ADMIN",
		PasswordHash: adminHash,
		Active:       true,
	}
	return am
}

func (a *AuthManager) SetUserHooks(lookup UserLookupFn, record RecordLoginFn) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.lookupFn = lookup
	a.recordFn = record
}

func (a *AuthManager) RegisterUser(email, displayName, role, password string) error {
	norm := strings.ToLower(strings.TrimSpace(email))
	if norm == "" || password == "" {
		return fmt.Errorf("email and password are required")
	}
	h, err := HashPasswordPBKDF2(password)
	if err != nil {
		return err
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.users[norm] = &AuthUser{
		ID:           "usr-" + hex.EncodeToString([]byte(norm))[:12],
		Email:        norm,
		DisplayName:  displayName,
		Role:         role,
		PasswordHash: h,
		Active:       true,
	}
	return nil
}

// Authenticate verifies credentials and returns (user, triesLeft, authenticated).
func (a *AuthManager) Authenticate(ctx context.Context, email, password string) (*AuthUser, int, bool) {
	norm := strings.ToLower(strings.TrimSpace(email))
	if norm == "" {
		return nil, maxLoginTries - 1, false
	}

	a.mu.Lock()
	lookup := a.lookupFn
	record := a.recordFn
	user := a.users[norm]
	a.mu.Unlock()

	if lookup != nil {
		if dbUser, err := lookup(ctx, norm); err == nil && dbUser != nil {
			user = dbUser
		}
	}

	a.mu.Lock()
	defer a.mu.Unlock()
	if user == nil || !user.Active || !VerifyPasswordPBKDF2(password, user.PasswordHash) {
		fails := a.failedTries[norm] + 1
		if fails > maxLoginTries {
			fails = maxLoginTries
		}
		a.failedTries[norm] = fails
		left := maxLoginTries - fails
		if record != nil {
			go record(context.Background(), norm, false)
		}
		return nil, left, false
	}

	delete(a.failedTries, norm)
	now := time.Now().UTC()
	prevLogin := user.LastLoginUTC
	user.LastLoginUTC = &now
	if record != nil {
		go record(context.Background(), norm, true)
	}
	copyUser := *user
	copyUser.LastLoginUTC = prevLogin
	return &copyUser, maxLoginTries, true
}

func (a *AuthManager) SignSession(user *AuthUser, ttl time.Duration) (string, error) {
	if user == nil {
		return "", fmt.Errorf("nil user")
	}
	claims := SessionClaims{
		UserID:      user.ID,
		Email:       user.Email,
		DisplayName: user.DisplayName,
		Role:        user.Role,
		ExpiresUnix: time.Now().UTC().Add(ttl).Unix(),
	}
	raw, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	payloadB64 := base64.RawURLEncoding.EncodeToString(raw)
	mac := hmac.New(sha256.New, a.signingKey)
	mac.Write([]byte(payloadB64))
	sigHex := hex.EncodeToString(mac.Sum(nil))
	return payloadB64 + "." + sigHex, nil
}

func (a *AuthManager) VerifySession(token string) (*SessionClaims, bool) {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 2 {
		return nil, false
	}
	gotSig, err := hex.DecodeString(parts[1])
	if err != nil {
		return nil, false
	}
	mac := hmac.New(sha256.New, a.signingKey)
	mac.Write([]byte(parts[0]))
	if subtle.ConstantTimeCompare(gotSig, mac.Sum(nil)) != 1 {
		return nil, false
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, false
	}
	var claims SessionClaims
	if err := json.Unmarshal(raw, &claims); err != nil {
		return nil, false
	}
	if time.Now().UTC().Unix() > claims.ExpiresUnix || claims.Email == "" {
		return nil, false
	}
	return &claims, true
}
