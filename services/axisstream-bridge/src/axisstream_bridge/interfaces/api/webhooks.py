"""HMAC-SHA256 signed outbound webhook dispatcher and verifier (ISO 27001)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx


def sign_webhook_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute X-Signature-256 header value: `sha256=<hexdigest>`."""
    digest = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
    """Constant-time verification of X-Signature-256 header."""
    expected = sign_webhook_payload(payload_bytes, secret)
    return hmac.compare_digest(expected.encode("utf-8"), signature_header.encode("utf-8"))


class HmacWebhookPublisher:
    """Dispatches signed JSON webhook events to registered consumer endpoints."""

    def __init__(self, webhook_url: str, secret: str, client: httpx.AsyncClient | None = None) -> None:
        self.webhook_url = webhook_url
        self._secret = secret
        self._client = client

    async def publish(self, event_type: str, payload: dict[str, Any]) -> httpx.Response | None:
        if not self.webhook_url:
            return None
        body = json.dumps(
            {"event_type": event_type, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        sig = sign_webhook_payload(body, self._secret)
        headers = {
            "Content-Type": "application/json",
            "X-Signature-256": sig,
        }
        if self._client is not None:
            return await self._client.post(self.webhook_url, content=body, headers=headers)
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(self.webhook_url, content=body, headers=headers)
