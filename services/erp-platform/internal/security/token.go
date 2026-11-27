package security

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strings"
)

const (
	DeviceTokenPrefix   = "dev_"
	ForecastTokenPrefix = "fcp_"
)

type resourceTokenPayload struct {
	Type      string   `json:"t"`
	ProjectID string   `json:"p"`
	DeviceID  string   `json:"d,omitempty"`
	Latitude  *float64 `json:"lat,omitempty"`
	Longitude *float64 `json:"lon,omitempty"`
	Version   int      `json:"v"`
}

// ResourceTokenCodec issues and verifies deterministic AES-256-GCM URL-safe opaque tokens
// for AxisTech devices (`dev_...`) and forecast points (`fcp_...`), preventing raw IDOR leakage.
type ResourceTokenCodec struct {
	key []byte
}

// NewResourceTokenCodec derives a 256-bit AES key from passphrase (or a deterministic local dev seed).
func NewResourceTokenCodec(passphrase string) *ResourceTokenCodec {
	seed := strings.TrimSpace(passphrase)
	if seed == "" {
		seed = "tbsgagtech-local-dev-seed"
	}
	sum := sha256.Sum256([]byte("tbsgagtech-token-v1|" + seed))
	return &ResourceTokenCodec{key: sum[:]}
}

func (c *ResourceTokenCodec) encryptPayload(p resourceTokenPayload) (string, error) {
	raw, err := json.Marshal(p)
	if err != nil {
		return "", fmt.Errorf("marshal token payload: %w", err)
	}
	block, err := aes.NewCipher(c.key)
	if err != nil {
		return "", fmt.Errorf("init cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("init gcm: %w", err)
	}
	mac := hmac.New(sha256.New, c.key)
	_, _ = mac.Write(raw)
	nonce := mac.Sum(nil)[:gcm.NonceSize()]
	sealed := gcm.Seal(nil, nonce, raw, []byte(p.Type))
	combined := append(nonce, sealed...)
	return base64.RawURLEncoding.EncodeToString(combined), nil
}

func (c *ResourceTokenCodec) decryptPayload(encoded, expectedType string) (*resourceTokenPayload, error) {
	blob, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		return nil, errors.New("malformed token encoding")
	}
	block, err := aes.NewCipher(c.key)
	if err != nil {
		return nil, fmt.Errorf("init cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("init gcm: %w", err)
	}
	ns := gcm.NonceSize()
	if len(blob) <= ns {
		return nil, errors.New("truncated resource token")
	}
	plain, err := gcm.Open(nil, blob[:ns], blob[ns:], []byte(expectedType))
	if err != nil {
		return nil, errors.New("resource token authentication failed")
	}
	var p resourceTokenPayload
	if err := json.Unmarshal(plain, &p); err != nil {
		return nil, errors.New("corrupted resource token payload")
	}
	if p.Type != expectedType || strings.TrimSpace(p.ProjectID) == "" {
		return nil, errors.New("invalid resource token claim")
	}
	return &p, nil
}

// EncodeDeviceToken seals a project+device pair into an opaque `dev_<base64url>` token.
func (c *ResourceTokenCodec) EncodeDeviceToken(projectID, deviceID string) (string, error) {
	if strings.TrimSpace(projectID) == "" || strings.TrimSpace(deviceID) == "" {
		return "", errors.New("project_id and device_id are required")
	}
	tok, err := c.encryptPayload(resourceTokenPayload{
		Type:      "dev",
		ProjectID: projectID,
		DeviceID:  deviceID,
		Version:   1,
	})
	if err != nil {
		return "", err
	}
	return DeviceTokenPrefix + tok, nil
}

// DecodeDeviceToken authenticates and unwraps a `dev_<base64url>` token.
func (c *ResourceTokenCodec) DecodeDeviceToken(token string) (string, string, error) {
	if !strings.HasPrefix(token, DeviceTokenPrefix) {
		return "", "", errors.New("device token must start with dev_")
	}
	p, err := c.decryptPayload(strings.TrimPrefix(token, DeviceTokenPrefix), "dev")
	if err != nil {
		return "", "", err
	}
	if strings.TrimSpace(p.DeviceID) == "" {
		return "", "", errors.New("missing device claim in token")
	}
	return p.ProjectID, p.DeviceID, nil
}

// EncodeForecastToken seals a project+WGS84 point into an opaque `fcp_<base64url>` token.
func (c *ResourceTokenCodec) EncodeForecastToken(projectID string, lat, lon float64) (string, error) {
	if strings.TrimSpace(projectID) == "" {
		return "", errors.New("project_id is required")
	}
	if math.IsNaN(lat) || math.IsInf(lat, 0) || lat < -90 || lat > 90 || math.IsNaN(lon) || math.IsInf(lon, 0) || lon < -180 || lon > 180 {
		return "", errors.New("WGS84 latitude/longitude out of bounds")
	}
	rlat := math.Round(lat*1e5) / 1e5
	rlon := math.Round(lon*1e5) / 1e5
	tok, err := c.encryptPayload(resourceTokenPayload{
		Type:      "fcp",
		ProjectID: projectID,
		Latitude:  &rlat,
		Longitude: &rlon,
		Version:   1,
	})
	if err != nil {
		return "", err
	}
	return ForecastTokenPrefix + tok, nil
}

// DecodeForecastToken authenticates and unwraps an `fcp_<base64url>` token.
func (c *ResourceTokenCodec) DecodeForecastToken(token string) (string, float64, float64, error) {
	if !strings.HasPrefix(token, ForecastTokenPrefix) {
		return "", 0, 0, errors.New("forecast token must start with fcp_")
	}
	p, err := c.decryptPayload(strings.TrimPrefix(token, ForecastTokenPrefix), "fcp")
	if err != nil {
		return "", 0, 0, err
	}
	if p.Latitude == nil || p.Longitude == nil || *p.Latitude < -90 || *p.Latitude > 90 || *p.Longitude < -180 || *p.Longitude > 180 {
		return "", 0, 0, errors.New("invalid WGS84 coordinate claim")
	}
	return p.ProjectID, *p.Latitude, *p.Longitude, nil
}
