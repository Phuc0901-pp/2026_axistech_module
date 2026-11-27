package security

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/tanbaocorp/axisstream-erp/internal/domain"
)

func TestGUT038_AES256GCMEncryptDecryptAndTamperReject(t *testing.T) {
	cipher, err := NewAESCipher("iso27001-strong-passphrase")
	if err != nil {
		t.Fatalf("NewAESCipher failed: %v", err)
	}
	plaintext := []byte(`{"audit":[{"id":"aud-1","details":"sensitive-erp-payload"}]}`)
	rawEnv, err := cipher.EncryptEnvelope(plaintext)
	if err != nil {
		t.Fatalf("EncryptEnvelope failed: %v", err)
	}
	if bytes.Contains(rawEnv, []byte("sensitive-erp-payload")) {
		t.Fatalf("ciphertext envelope leaked plaintext: %s", string(rawEnv))
	}

	var meta EncryptedEnvelope
	if err := json.Unmarshal(rawEnv, &meta); err != nil || !meta.Encrypted || meta.Algorithm != AlgorithmAES256GCM {
		t.Fatalf("unexpected envelope metadata: %s (%v)", string(rawEnv), err)
	}

	decoded, wasEnc, err := cipher.DecryptEnvelope(rawEnv)
	if err != nil || !wasEnc || !bytes.Equal(decoded, plaintext) {
		t.Fatalf("DecryptEnvelope failed: wasEnc=%v err=%v", wasEnc, err)
	}

	wrongCipher, _ := NewAESCipher("wrong-passphrase")
	if _, _, err := wrongCipher.DecryptEnvelope(rawEnv); err == nil {
		t.Fatal("expected decryption failure with wrong passphrase")
	}

	tampered := bytes.Replace(rawEnv, []byte(`"v"`), []byte(`"x"`), 1)
	if bytes.Equal(tampered, rawEnv) {
		tampered = append([]byte{}, rawEnv...)
		tampered[len(tampered)-4] ^= 0xFF
	}
	if _, _, err := cipher.DecryptEnvelope(tampered); err == nil {
		t.Fatal("expected tamper detection failure on modified envelope")
	}
}

func TestGUT039_AuditHashChainIntegrityAndTamperDetect(t *testing.T) {
	ts := time.Date(2026, 11, 27, 9, 0, 0, 0, time.UTC)
	e1 := domain.AuditEntry{
		ID: "aud-1", TimestampUTC: ts, Actor: "system", Action: "SYNC",
		ResourceType: "projects", ResourceID: "p1", CorrelationID: "cid-1", Details: "synced=1",
	}
	e1.PrevHash = "GENESIS"
	e1.EntryHash = ComputeAuditHash(e1.PrevHash, e1)

	e2 := domain.AuditEntry{
		ID: "aud-2", TimestampUTC: ts.Add(time.Minute), Actor: "operator", Action: "ACKNOWLEDGE_INCIDENT",
		ResourceType: "incident", ResourceID: "inc-1", CorrelationID: "cid-2", Details: "acknowledged",
	}
	e2.PrevHash = e1.EntryHash
	e2.EntryHash = ComputeAuditHash(e2.PrevHash, e2)

	if !VerifyAuditChain([]domain.AuditEntry{e1, e2}) {
		t.Fatal("expected valid audit chain")
	}

	tampered := []domain.AuditEntry{e1, e2}
	tampered[0].Details = "forged-details"
	if VerifyAuditChain(tampered) {
		t.Fatal("expected VerifyAuditChain to fail when entry details are modified")
	}
}

func TestGUT049_OpaqueResourceTokenAES256GCMAndTamperReject(t *testing.T) {
	codec := NewResourceTokenCodec("tbsgagtech-master-secret")

	devTok, err := codec.EncodeDeviceToken("proj-tbsg-1", "dev-weather-79DAAFB4")
	if err != nil {
		t.Fatalf("EncodeDeviceToken failed: %v", err)
	}
	if !strings.HasPrefix(devTok, DeviceTokenPrefix) || strings.Contains(devTok, "79DAAFB4") {
		t.Fatalf("device token must be opaque dev_... without plaintext leakage, got %q", devTok)
	}
	devTok2, _ := codec.EncodeDeviceToken("proj-tbsg-1", "dev-weather-79DAAFB4")
	if devTok != devTok2 {
		t.Fatal("expected deterministic device token for stable bookmarking")
	}
	pid, did, err := codec.DecodeDeviceToken(devTok)
	if err != nil || pid != "proj-tbsg-1" || did != "dev-weather-79DAAFB4" {
		t.Fatalf("DecodeDeviceToken failed: pid=%q did=%q err=%v", pid, did, err)
	}
	if _, _, err := codec.DecodeDeviceToken(devTok + "X"); err == nil {
		t.Fatal("expected tampered device token rejection")
	}

	fcTok, err := codec.EncodeForecastToken("proj-tbsg-1", 11.6901, 106.8495)
	if err != nil || !strings.HasPrefix(fcTok, ForecastTokenPrefix) {
		t.Fatalf("EncodeForecastToken failed: %q err=%v", fcTok, err)
	}
	fpid, lat, lon, err := codec.DecodeForecastToken(fcTok)
	if err != nil || fpid != "proj-tbsg-1" || lat != 11.6901 || lon != 106.8495 {
		t.Fatalf("DecodeForecastToken failed: %q %f %f err=%v", fpid, lat, lon, err)
	}
	if _, _, _, err := NewResourceTokenCodec("wrong-key").DecodeForecastToken(fcTok); err == nil {
		t.Fatal("expected wrong key to reject forecast token")
	}
}
