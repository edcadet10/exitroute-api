"""Per-client webhook subscription and delivery history API."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select

from exitroute.api.deps import SessionDep, SettingsDep, WebhookManager
from exitroute.domain.security import (
    InvalidCursorError,
    UnsafeWebhookUrlError,
    decode_cursor,
    derive_webhook_secret,
    encode_cursor,
    validate_webhook_url,
)
from exitroute.errors import bad_request, not_found, unprocessable
from exitroute.models import WebhookDelivery, WebhookSubscription
from exitroute.schemas import (
    WebhookDeliveryPage,
    WebhookDeliveryView,
    WebhookSecretRotated,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionView,
)
from exitroute.services.auth import audit

router = APIRouter(prefix="/v1/webhook-subscriptions", tags=["webhooks"])


def _owned_subscription(
    session: SessionDep, subscription_id: uuid.UUID, client_id: uuid.UUID
) -> WebhookSubscription:
    subscription = session.scalar(
        select(WebhookSubscription).where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.client_id == client_id,
        )
    )
    if subscription is None:
        raise not_found("webhook_not_found", "The requested webhook subscription does not exist.")
    return subscription


@router.post(
    "",
    operation_id="createWebhookSubscription",
    response_model=WebhookSubscriptionCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    body: WebhookSubscriptionCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    principal: WebhookManager,
) -> WebhookSubscriptionCreated:
    assert principal.client_id is not None
    url = str(body.url)
    try:
        validate_webhook_url(url)
    except UnsafeWebhookUrlError as exc:
        raise unprocessable("unsafe_webhook_url", str(exc)) from exc
    subscription = WebhookSubscription(
        client_id=principal.client_id,
        url=url,
        event_types=sorted(body.event_types),
        secret_salt=secrets.token_bytes(32),
    )
    session.add(subscription)
    session.flush()
    secret = derive_webhook_secret(
        settings.webhook_master_secret.get_secret_value(),
        subscription.id,
        subscription.secret_salt,
    )
    audit(
        session,
        principal,
        "webhook.created",
        "webhook_subscription",
        str(subscription.id),
        request_id=getattr(request.state, "request_id", None),
    )
    return WebhookSubscriptionCreated(
        id=subscription.id,
        url=subscription.url,
        event_types=subscription.event_types,
        active=subscription.active,
        created_at=subscription.created_at,
        signing_secret=secret,
    )


@router.get(
    "", operation_id="listWebhookSubscriptions", response_model=list[WebhookSubscriptionView]
)
def list_subscriptions(
    session: SessionDep,
    principal: WebhookManager,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[WebhookSubscriptionView]:
    assert principal.client_id is not None
    records = session.scalars(
        select(WebhookSubscription)
        .where(WebhookSubscription.client_id == principal.client_id)
        .order_by(WebhookSubscription.created_at.desc())
        .limit(limit)
    )
    return [WebhookSubscriptionView.model_validate(record) for record in records]


@router.get(
    "/{subscription_id}",
    operation_id="getWebhookSubscription",
    response_model=WebhookSubscriptionView,
)
def get_subscription(
    subscription_id: uuid.UUID,
    session: SessionDep,
    principal: WebhookManager,
) -> WebhookSubscriptionView:
    assert principal.client_id is not None
    return WebhookSubscriptionView.model_validate(
        _owned_subscription(session, subscription_id, principal.client_id)
    )


@router.post(
    "/{subscription_id}/rotate-secret",
    operation_id="rotateWebhookSecret",
    response_model=WebhookSecretRotated,
)
def rotate_subscription_secret(
    subscription_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    principal: WebhookManager,
) -> WebhookSecretRotated:
    assert principal.client_id is not None
    subscription = _owned_subscription(session, subscription_id, principal.client_id)
    subscription.secret_salt = secrets.token_bytes(32)
    secret = derive_webhook_secret(
        settings.webhook_master_secret.get_secret_value(), subscription.id, subscription.secret_salt
    )
    audit(
        session,
        principal,
        "webhook.secret_rotated",
        "webhook_subscription",
        str(subscription.id),
        request_id=getattr(request.state, "request_id", None),
    )
    return WebhookSecretRotated(id=subscription.id, signing_secret=secret)


@router.delete(
    "/{subscription_id}",
    operation_id="deleteWebhookSubscription",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subscription(
    subscription_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: WebhookManager,
) -> None:
    assert principal.client_id is not None
    subscription = _owned_subscription(session, subscription_id, principal.client_id)
    subscription.active = False
    audit(
        session,
        principal,
        "webhook.deactivated",
        "webhook_subscription",
        str(subscription.id),
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/{subscription_id}/deliveries",
    operation_id="listWebhookDeliveries",
    response_model=WebhookDeliveryPage,
)
def list_deliveries(
    subscription_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    principal: WebhookManager,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> WebhookDeliveryPage:
    assert principal.client_id is not None
    _owned_subscription(session, subscription_id, principal.client_id)
    payload: dict[str, Any] = {}
    if cursor:
        try:
            payload = decode_cursor(settings.cursor_secret.get_secret_value(), cursor)
        except InvalidCursorError as exc:
            raise bad_request("invalid_cursor", str(exc)) from exc
        if payload.get("kind") != "deliveries" or payload.get("subscription_id") != str(
            subscription_id
        ):
            raise bad_request("cursor_scope_mismatch", "This cursor belongs to another collection.")
    before = payload.get("before")
    statement = select(WebhookDelivery).where(WebhookDelivery.subscription_id == subscription_id)
    if before:
        try:
            before_at = datetime.fromisoformat(str(before))
        except ValueError as exc:
            raise bad_request(
                "invalid_cursor", "The delivery cursor timestamp is invalid."
            ) from exc
        statement = statement.where(WebhookDelivery.created_at < before_at)
    records = list(
        session.scalars(statement.order_by(WebhookDelivery.created_at.desc()).limit(limit + 1))
    )
    has_more = len(records) > limit
    records = records[:limit]
    next_cursor = None
    if has_more and records:
        next_cursor = encode_cursor(
            settings.cursor_secret.get_secret_value(),
            {
                "kind": "deliveries",
                "subscription_id": str(subscription_id),
                "before": records[-1].created_at.isoformat(),
            },
            settings.cursor_ttl_seconds,
        )
    return WebhookDeliveryPage(
        data=[WebhookDeliveryView.model_validate(record) for record in records],
        next_cursor=next_cursor,
    )
