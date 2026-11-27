"""ISO 27001 Field & Payload Encryption using pure-stdlib HKDF-SHA256 + CTR + HMAC-SHA256."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from axisstream_bridge.core.exceptions import SecurityViolationError


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    """Derive cryptographic subkey material following RFC 5869 HKDF-SHA256."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(enc_key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


class FieldEncryptor:
    """Authenticated Encryption (Encrypt-then-MAC) for persisted bridge payloads."""

    PREFIX = "ENC:v1:"
    ALGORITHM = "HKDF-SHA256-CTR-HMAC-SHA256"

    def __init__(self, secret_key: str = "") -> None:
        raw = secret_key.strip().encode("utf-8")
        self._enabled = bool(raw)
        if self._enabled:
            salt = hashlib.sha256(b"axistech-bridge-salt-v1").digest()
            self._enc_key = _hkdf_sha256(raw, salt, b"payload-enc", 32)
            self._mac_key = _hkdf_sha256(raw, salt, b"payload-mac", 32)
        else:
            self._enc_key = b""
            self._mac_key = b""

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def algorithm(self) -> str:
        return self.ALGORITHM if self._enabled else "NONE"

    def encrypt_text(self, plaintext: str) -> str:
        if not self._enabled:
            return plaintext
        data = plaintext.encode("utf-8")
        nonce = secrets.token_bytes(16)
        ks = _keystream(self._enc_key, nonce, len(data))
        ciphertext = bytes(a ^ b for a, b in zip(data, ks))
        tag = hmac.new(self._mac_key, b"v1|" + nonce + ciphertext, hashlib.sha256).digest()
        return (
            f"{self.PREFIX}"
            f"{base64.urlsafe_b64encode(nonce).decode('ascii')}:"
            f"{base64.urlsafe_b64encode(ciphertext).decode('ascii')}:"
            f"{base64.urlsafe_b64encode(tag).decode('ascii')}"
        )

    def decrypt_text(self, token: str) -> str:
        if not isinstance(token, str) or not token.startswith(self.PREFIX):
            return token
        if not self._enabled:
            raise SecurityViolationError(
                "Encrypted payload encountered but AXISSTREAM_ENCRYPTION_KEY is not configured"
            )
        parts = token[len(self.PREFIX) :].split(":")
        if len(parts) != 3:
            raise SecurityViolationError("Malformed encrypted payload envelope")
        try:
            nonce = base64.urlsafe_b64decode(parts[0].encode("ascii"))
            ciphertext = base64.urlsafe_b64decode(parts[1].encode("ascii"))
            tag = base64.urlsafe_b64decode(parts[2].encode("ascii"))
        except Exception as exc:
            raise SecurityViolationError("Invalid base64 encoding in encrypted payload") from exc

        expected_tag = hmac.new(
            self._mac_key, b"v1|" + nonce + ciphertext, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise SecurityViolationError(
                "Encrypted payload integrity check failed (tampered data or invalid key)"
            )
        ks = _keystream(self._enc_key, nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, ks))
        return plaintext.decode("utf-8")
