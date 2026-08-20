"""Transactional-outbox leasing and SSRF-resistant webhook delivery."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import time
import uuid
from datetime import timedelta
from typing import Protocol

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from exitroute.config import Settings
from exitroute.domain.security import (
    UnsafeWebhookUrlError,
    derive_webhook_secret,
    sign_webhook,
    validate_webhook_url,
)
from exitroute.models import WebhookDelivery, WebhookSubscription
from exitroute.services.auth import utcnow

logger = logging.getLogger(__name__)


class HttpSender(Protocol):
    def send(self, request: httpx.Request) -> httpx.Response: ...


def _lease_due(session: Session, settings: Settings, limit: int) -> list[uuid.UUID]:
    now = utcnow()
    available = or_(
        (
            WebhookDelivery.state.in_(["pending", "retrying"])
            & (WebhookDelivery.next_attempt_at <= now)
        ),
        ((WebhookDelivery.state == "delivering") & (WebhookDelivery.lease_until < now)),
    )
    records = list(
        session.scalars(
            select(WebhookDelivery)
            .where(available)
            .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    )
    lease_until = now + timedelta(seconds=settings.webhook_lease_seconds)
    for record in records:
        record.state = "delivering"
        record.lease_until = lease_until
    session.commit()
    return [record.id for record in records]


def _pinned_url(original: str, address: str) -> httpx.URL:
    url = httpx.URL(original)
    host = f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
    return url.copy_with(host=host)


def _retry_delay(delivery_id: uuid.UUID, attempt: int) -> int:
    base: int = min(3600, 2 ** min(attempt, 11))
    jitter_seed = hashlib.sha256(f"{delivery_id}:{attempt}".encode()).digest()
    jitter = int.from_bytes(jitter_seed[:2], "big") % max(1, base // 4)
    return base + jitter


def _mark_failure(
    delivery: WebhookDelivery,
    settings: Settings,
    message: str,
    *,
    status_code: int | None = None,
    retryable: bool = True,
) -> None:
    delivery.last_error = message[:500]
    delivery.last_status_code = status_code
    delivery.lease_until = None
    exhausted = delivery.attempt_count >= settings.webhook_max_attempts
    if exhausted or not retryable:
        delivery.state = "dead"
    else:
        delivery.state = "retrying"
        delivery.next_attempt_at = utcnow() + timedelta(
            seconds=_retry_delay(delivery.id, delivery.attempt_count)
        )


def _send_one(
    session: Session,
    settings: Settings,
    delivery_id: uuid.UUID,
    sender: HttpSender,
) -> None:
    delivery = session.get(WebhookDelivery, delivery_id)
    if delivery is None or delivery.state != "delivering":
        return
    subscription = session.get(WebhookSubscription, delivery.subscription_id)
    if subscription is None or not subscription.active:
        _mark_failure(delivery, settings, "subscription is inactive", retryable=False)
        return
    delivery.attempt_count += 1
    try:
        host, addresses = validate_webhook_url(subscription.url)
    except UnsafeWebhookUrlError as exc:
        _mark_failure(delivery, settings, f"unsafe destination: {exc}", retryable=False)
        return
    address = addresses[(delivery.attempt_count - 1) % len(addresses)]
    body = json.dumps(delivery.payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = int(time.time())
    secret = derive_webhook_secret(
        settings.webhook_master_secret.get_secret_value(),
        subscription.id,
        subscription.secret_salt,
    )
    signature = sign_webhook(secret, timestamp, body)
    request = httpx.Request(
        "POST",
        _pinned_url(subscription.url, address),
        headers={
            "Content-Type": "application/json",
            "Connection": "close",
            "Host": host,
            "User-Agent": "ExitRoute-Webhook/0.1",
            "X-ExitRoute-Delivery": str(delivery.id),
            "X-ExitRoute-Event": str(delivery.payload.get("type", "unknown")),
            "X-ExitRoute-Signature": f"v1={signature}",
            "X-ExitRoute-Timestamp": str(timestamp),
        },
        content=body,
        extensions={"sni_hostname": host},
    )
    try:
        response = sender.send(request)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
        _mark_failure(delivery, settings, f"network error: {type(exc).__name__}")
        return
    delivery.last_status_code = response.status_code
    delivery.lease_until = None
    if 200 <= response.status_code < 300:
        delivery.state = "delivered"
        delivery.delivered_at = utcnow()
        delivery.last_error = None
        return
    retryable = response.status_code in {408, 425, 429} or response.status_code >= 500
    _mark_failure(
        delivery,
        settings,
        f"endpoint returned HTTP {response.status_code}",
        status_code=response.status_code,
        retryable=retryable,
    )


def process_due_deliveries(
    factory: sessionmaker[Session],
    settings: Settings,
    *,
    limit: int = 50,
    sender: HttpSender | None = None,
) -> int:
    """Lease and attempt a bounded outbox batch. Safe across worker replicas."""

    with factory() as session:
        delivery_ids = _lease_due(session, settings, limit)
    owned_sender = sender is None
    client: HttpSender = sender or httpx.Client(
        timeout=httpx.Timeout(settings.webhook_timeout_seconds),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        for delivery_id in delivery_ids:
            with factory() as session:
                try:
                    _send_one(session, settings, delivery_id, client)
                    session.commit()
                except Exception:
                    session.rollback()
                    logger.exception(
                        "unexpected webhook delivery failure",
                        extra={"delivery_id": delivery_id},
                    )
    finally:
        if owned_sender and isinstance(client, httpx.Client):
            client.close()
    return len(delivery_ids)
