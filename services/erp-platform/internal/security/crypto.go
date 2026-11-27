package security

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
)

const AlgorithmAES256GCM = "AES-256-GCM"

// EncryptedEnvelope wraps ciphertext persisted on disk with AES-256-GCM metadata.
type EncryptedEnvelope struct {
	Encrypted     bool   `json:"encrypted"`
	Version       int    `json:"version"`
	Algorithm     string `json:"algorithm"`
	NonceB64      string `json:"nonce_b64"`
	CiphertextB64 string `json:"ciphertext_b64"`
}

// AESCipher provides ISO 27001 compliant authenticated encryption at rest.
type AESCipher struct {
	key []byte
}

// NewAESCipher derives a 256-bit key from a non-empty passphrase via SHA-256.
func NewAESCipher(passphrase string) (*AESCipher, error) {
	trimmed := strings.TrimSpace(passphrase)
	if trimmed == "" {
		return nil, errors.New("encryption passphrase must not be empty")
	}
	sum := sha256.Sum256([]byte("axistech-erp-at-rest-v1|" + trimmed))
	return &AESCipher{key: sum[:]}, nil
}

// EncryptEnvelope encrypts plaintext bytes with a fresh 12-byte CSPRNG nonce using AES-256-GCM.
func (c *AESCipher) EncryptEnvelope(plaintext []byte) ([]byte, error) {
	block, err := aes.NewCipher(c.key)
	if err != nil {
		return nil, fmt.Errorf("aes cipher init: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm init: %w", err)
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("nonce generation: %w", err)
	}
	ciphertext := gcm.Seal(nil, nonce, plaintext, []byte(AlgorithmAES256GCM))
	env := EncryptedEnvelope{
		Encrypted:     true,
		Version:       1,
		Algorithm:     AlgorithmAES256GCM,
		NonceB64:      base64.StdEncoding.EncodeToString(nonce),
		CiphertextB64: base64.StdEncoding.EncodeToString(ciphertext),
	}
	return json.Marshal(env)
}

// DecryptEnvelope decodes an encrypted envelope; legacy plaintext JSON passes through with wasEncrypted=false.
func (c *AESCipher) DecryptEnvelope(raw []byte) ([]byte, bool, error) {
	var env EncryptedEnvelope
	if err := json.Unmarshal(raw, &env); err == nil && env.Encrypted {
		if c == nil {
			return nil, true, errors.New("encrypted state file requires ERP_ENCRYPTION_KEY")
		}
		if env.Algorithm != AlgorithmAES256GCM {
			return nil, true, fmt.Errorf("unsupported encryption algorithm %q", env.Algorithm)
		}
		nonce, err := base64.StdEncoding.DecodeString(env.NonceB64)
		if err != nil {
			return nil, true, fmt.Errorf("decode nonce: %w", err)
		}
		ciphertext, err := base64.StdEncoding.DecodeString(env.CiphertextB64)
		if err != nil {
			return nil, true, fmt.Errorf("decode ciphertext: %w", err)
		}
		block, err := aes.NewCipher(c.key)
		if err != nil {
			return nil, true, fmt.Errorf("aes cipher init: %w", err)
		}
		gcm, err := cipher.NewGCM(block)
		if err != nil {
			return nil, true, fmt.Errorf("gcm init: %w", err)
		}
		plain, err := gcm.Open(nil, nonce, ciphertext, []byte(AlgorithmAES256GCM))
		if err != nil {
			return nil, true, fmt.Errorf("decrypt/verify AES-256-GCM payload failed: %w", err)
		}
		return plain, true, nil
	}
	return raw, false, nil
}

// ComputeAuditHash computes a deterministic SHA-256 hash linking an audit entry to prevHash.
func ComputeAuditHash(prevHash string, entry domain.AuditEntry) string {
	canonical := fmt.Sprintf(
		"%s|%s|%s|%s|%s|%s|%s|%s|%s",
		prevHash,
		entry.ID,
		entry.TimestampUTC.UTC().Format(time.RFC3339Nano),
		entry.Actor,
		entry.Action,
		entry.ResourceType,
		entry.ResourceID,
		entry.CorrelationID,
		entry.Details,
	)
	sum := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(sum[:])
}

// VerifyAuditChain validates that every entry's prev_hash and entry_hash form an unbroken chain.
func VerifyAuditChain(entries []domain.AuditEntry) bool {
	expectedPrev := "GENESIS"
	for _, entry := range entries {
		if entry.PrevHash == "" && entry.EntryHash == "" {
			continue
		}
		if entry.PrevHash != expectedPrev {
			return false
		}
		if ComputeAuditHash(expectedPrev, entry) != entry.EntryHash {
			return false
		}
		expectedPrev = entry.EntryHash
	}
	return true
}
