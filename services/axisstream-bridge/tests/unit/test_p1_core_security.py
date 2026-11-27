"""Prompt 1 Unit Tests (UT-001 to UT-005): Config, SecretStr, JSON Log Redaction, Exceptions."""

from __future__ import annotations

import json
import logging

import pytest

from axisstream_bridge.core.config import BridgeSettings
from axisstream_bridge.core.exceptions import (
    AuthenticationError,
    RateLimitError,
    UpstreamTransientError,
)
from axisstream_bridge.core.logging import (
    REDACTED,
    JsonFormatter,
    correlation_id_var,
    get_or_create_correlation_id,
)


def test_ut_001_config_validation_https_and_live_creds() -> None:
    cfg = BridgeSettings(mode="demo")
    assert cfg.v2_base_url.startswith("https://")

    with pytest.raises(ValueError, match="https://"):
        BridgeSettings(v2_base_url="http://v2.api.axisstream.co")

    with pytest.raises(ValueError, match="allowed suffix"):
        BridgeSettings(v2_base_url="https://evil.example.com")

    with pytest.raises(ValueError, match="requires"):
        BridgeSettings(mode="live", auth_mode="cookie")


def test_ut_002_secret_str_never_exposed_in_repr_or_str() -> None:
    secret_pw = "SuperSecretValue!999"
    secret_tok = "tok_secret_value_abc"
    cfg = BridgeSettings(
        mode="live",
        auth_mode="dual",
        axisstream_username="operator@example.com",
        axisstream_password=secret_pw,
        axisstream_exchange_token=secret_tok,
        inbound_api_key="inbound_secret_xyz",
    )
    rendered = f"{repr(cfg)} {str(cfg)}"
    assert secret_pw not in rendered
    assert secret_tok not in rendered
    assert "inbound_secret_xyz" not in rendered


def test_ut_003_log_redaction_masks_sensitive_keys_and_inline_headers() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="axisstream_bridge.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Auth header Bearer my.jwt.token Cookie: sid=secret123",
        args=(),
        exc_info=None,
    )
    record.password = "plain-pw"
    record.nested = {"cookie": "abc", "token": "xyz", "safe": "ok"}

    output = formatter.format(record)
    parsed = json.loads(output)
    assert "plain-pw" not in output
    assert "my.jwt.token" not in output
    assert "secret123" not in output
    assert parsed["extra"]["password"] == REDACTED
    assert parsed["extra"]["nested"]["cookie"] == REDACTED
    assert parsed["extra"]["nested"]["token"] == REDACTED
    assert parsed["extra"]["nested"]["safe"] == "ok"


def test_ut_004_correlation_id_propagation_and_generation() -> None:
    token = correlation_id_var.set("")
    try:
        auto_id = get_or_create_correlation_id()
        assert len(auto_id) == 36
        assert get_or_create_correlation_id() == auto_id

        explicit = get_or_create_correlation_id("cid-custom-123")
        assert explicit == "cid-custom-123"
        assert get_or_create_correlation_id() == "cid-custom-123"
    finally:
        correlation_id_var.reset(token)


def test_ut_005_error_taxonomy_and_details_redaction() -> None:
    err1 = AuthenticationError("bad creds", details={"password": "123", "user": "op"})
    assert err1.code == "AUTHENTICATION_FAILED"
    assert err1.retryable is False
    assert err1.http_status_hint == 401
    assert err1.details["password"] == REDACTED

    err2 = RateLimitError(retry_after=5.0)
    assert err2.retryable is True
    assert err2.http_status_hint == 429
    assert err2.retry_after == 5.0

    err3 = UpstreamTransientError("503")
    assert err3.retryable is True
    assert err3.http_status_hint == 502
