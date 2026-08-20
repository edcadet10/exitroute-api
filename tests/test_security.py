from __future__ import annotations

import socket
import uuid

import pytest
from pydantic import ValidationError

from exitroute.config import Settings
from exitroute.domain.security import (
    InvalidCursorError,
    UnsafeWebhookUrlError,
    contains_sensitive_text,
    decode_cursor,
    derive_webhook_secret,
    encode_cursor,
    generate_api_key,
    sign_webhook,
    validate_webhook_url,
    verify_api_key,
)


def test_api_key_is_random_and_verified_with_keyed_digest() -> None:
    first = generate_api_key("pepper-that-is-long-enough-for-a-test")
    second = generate_api_key("pepper-that-is-long-enough-for-a-test")
    assert first.plaintext.startswith("er_live_")
    assert first.plaintext != second.plaintext
    assert verify_api_key("pepper-that-is-long-enough-for-a-test", first.plaintext, first.digest)
    assert not verify_api_key("wrong-pepper", first.plaintext, first.digest)


def test_cursor_rejects_tampering_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("exitroute.domain.security.time.time", lambda: 1_000)
    cursor = encode_cursor("cursor-secret", {"kind": "test", "after": 4}, 60)
    assert decode_cursor("cursor-secret", cursor)["after"] == 4
    with pytest.raises(InvalidCursorError, match="signature"):
        decode_cursor("another-secret", cursor)
    monkeypatch.setattr("exitroute.domain.security.time.time", lambda: 1_061)
    with pytest.raises(InvalidCursorError, match="expired"):
        decode_cursor("cursor-secret", cursor)


@pytest.mark.parametrize(
    "value",
    [
        "email me at person@example.com",
        "call +1 (212) 555-0199",
        "my password changed",
        "screenshot at https://private.example/path",
        "4242 4242 4242 4242",
    ],
)
def test_sensitive_observation_text_is_detected(value: str) -> None:
    assert contains_sensitive_text(value)


def test_webhook_url_rejects_internal_networks(monkeypatch: pytest.MonkeyPatch) -> None:
    def public_records(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", public_records)
    assert validate_webhook_url("https://hooks.example.com/events") == (
        "hooks.example.com",
        ("8.8.8.8",),
    )

    def private_records(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", private_records)
    with pytest.raises(UnsafeWebhookUrlError, match="non-public"):
        validate_webhook_url("https://hooks.example.com/events")
    with pytest.raises(UnsafeWebhookUrlError, match="HTTPS"):
        validate_webhook_url("http://hooks.example.com/events")


def test_webhook_secret_derivation_and_signing_are_stable() -> None:
    subscription_id = uuid.UUID("f70e2cf8-eec5-4c7c-bd04-e1a51129da02")
    secret = derive_webhook_secret("master-secret", subscription_id, b"x" * 32)
    assert secret.startswith("whsec_")
    assert sign_webhook(secret, 1234, b"{}") == sign_webhook(secret, 1234, b"{}")
    assert sign_webhook(secret, 1234, b"{}") != sign_webhook(secret, 1235, b"{}")


def test_production_configuration_rejects_defaults_and_secret_reuse() -> None:
    with pytest.raises(ValidationError, match="bootstrap admin"):
        Settings(environment="production", public_base_url="https://api.example.com")
    with pytest.raises(ValidationError, match="must not be reused"):
        Settings(
            environment="production",
            public_base_url="https://api.example.com",
            bootstrap_admin_enabled=False,
            api_key_pepper="x" * 40,
            cursor_secret="y" * 40,
            webhook_master_secret="x" * 40,
        )
    settings = Settings(
        environment="production",
        public_base_url="https://api.example.com",
        bootstrap_admin_enabled=False,
        api_key_pepper="a" * 40,
        cursor_secret="b" * 40,
        webhook_master_secret="c" * 40,
    )
    assert settings.environment == "production"
