"""Key generation, keyed digests, cursors, webhook signing, and privacy filters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

_PII_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+?1[-. (]*)?(?:\d{3}[-. )]*){2}\d{4}(?!\d)"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b(?:password|passcode|session[_ -]?id|cookie|auth(?:orization)? token)\b", re.I),
    re.compile(r"https?://", re.I),
)


class InvalidCursorError(ValueError):
    pass


class UnsafeWebhookUrlError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedApiKey:
    plaintext: str
    prefix: str
    digest: bytes


def keyed_digest(secret: str, value: str) -> bytes:
    return hmac.digest(secret.encode(), value.encode(), "sha256")


def generate_api_key(pepper: str) -> GeneratedApiKey:
    plaintext = f"er_live_{secrets.token_urlsafe(32)}"
    return GeneratedApiKey(
        plaintext=plaintext,
        prefix=plaintext[:16],
        digest=keyed_digest(pepper, plaintext),
    )


def verify_api_key(pepper: str, candidate: str, expected: bytes) -> bool:
    return hmac.compare_digest(keyed_digest(pepper, candidate), expected)


def contains_sensitive_text(value: str | None) -> bool:
    return bool(value and any(pattern.search(value) for pattern in _PII_PATTERNS))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def encode_cursor(secret: str, payload: dict[str, Any], ttl_seconds: int) -> str:
    document = {**payload, "exp": int(time.time()) + ttl_seconds}
    body = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.digest(secret.encode(), body, "sha256")
    return f"{_b64encode(body)}.{_b64encode(signature)}"


def decode_cursor(secret: str, cursor: str) -> dict[str, Any]:
    try:
        body_part, signature_part = cursor.split(".", 1)
        body = _b64decode(body_part)
        signature = _b64decode(signature_part)
        expected = hmac.digest(secret.encode(), body, "sha256")
        if not hmac.compare_digest(signature, expected):
            raise InvalidCursorError("cursor signature is invalid")
        payload = json.loads(body)
        if not isinstance(payload, dict) or int(payload["exp"]) < int(time.time()):
            raise InvalidCursorError("cursor has expired")
        return payload
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, InvalidCursorError):
            raise
        raise InvalidCursorError("cursor is malformed") from exc


def derive_webhook_secret(master: str, subscription_id: uuid.UUID, salt: bytes) -> str:
    material = subscription_id.bytes + salt
    return f"whsec_{_b64encode(hmac.digest(master.encode(), material, 'sha256'))}"


def sign_webhook(secret: str, timestamp: int, body: bytes) -> str:
    value = str(timestamp).encode() + b"." + body
    return hmac.new(secret.encode(), value, hashlib.sha256).hexdigest()


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_webhook_url(url: str) -> tuple[str, tuple[str, ...]]:
    """Resolve and reject URLs capable of reaching non-public network space."""

    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeWebhookUrlError("webhook URL must be absolute HTTPS")
    if parsed.username or parsed.password or parsed.fragment:
        raise UnsafeWebhookUrlError("webhook URL cannot include credentials or a fragment")
    if parsed.port not in (None, 443):
        raise UnsafeWebhookUrlError("webhook URL must use port 443")
    host = parsed.hostname.rstrip(".")
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeWebhookUrlError("webhook host could not be resolved") from exc
    addresses = tuple(sorted({str(record[4][0]) for record in records}))
    if not addresses or not all(_is_public_address(address) for address in addresses):
        raise UnsafeWebhookUrlError("webhook host resolves to a non-public address")
    return host, addresses
