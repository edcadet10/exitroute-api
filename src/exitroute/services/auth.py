"""API-client authentication, scopes, quotas, and credential lifecycle."""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from exitroute.config import Settings
from exitroute.domain.security import generate_api_key, verify_api_key
from exitroute.errors import ApiProblemError, forbidden, unauthorized
from exitroute.models import ApiClient, ApiKey, AuditEvent, RateWindow
from exitroute.schemas import ApiKeyCreate


@dataclass(frozen=True)
class Principal:
    actor: str
    client_id: uuid.UUID | None
    key_id: uuid.UUID | None
    scopes: frozenset[str]
    bootstrap: bool = False


def utcnow() -> datetime:
    return datetime.now(UTC)


def audit(
    session: Session,
    principal: Principal,
    action: str,
    object_type: str,
    object_id: str,
    *,
    request_id: str | None = None,
    context: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor=principal.actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            request_id=request_id,
            context=context or {},
        )
    )


def _increment_rate_window(
    session: Session, client: ApiClient, settings: Settings
) -> tuple[int, int]:
    now = utcnow()
    window = now.replace(second=0, microsecond=0)
    limit = client.rate_limit_per_minute or settings.rate_limit_per_minute
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = (
            pg_insert(RateWindow)
            .values(client_id=client.id, window_start=window, request_count=1)
            .on_conflict_do_update(
                constraint="uq_rate_window",
                set_={"request_count": RateWindow.request_count + 1},
            )
            .returning(RateWindow.request_count)
        )
        count = session.scalar(statement)
        assert count is not None
    else:
        record = session.scalar(
            select(RateWindow).where(
                RateWindow.client_id == client.id, RateWindow.window_start == window
            )
        )
        if record is None:
            record = RateWindow(client_id=client.id, window_start=window, request_count=1)
            session.add(record)
        else:
            record.request_count += 1
        session.flush()
        count = record.request_count
    return count, limit


def authenticate_api_key(session: Session, settings: Settings, candidate: str | None) -> Principal:
    if not candidate or len(candidate) > 128 or not candidate.startswith("er_live_"):
        raise unauthorized("invalid_api_key", "A valid X-API-Key header is required.")
    prefix = candidate[:16]
    key = session.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))
    if key is None or not verify_api_key(
        settings.api_key_pepper.get_secret_value(), candidate, key.secret_digest
    ):
        raise unauthorized("invalid_api_key", "The supplied API key is invalid.")
    now = utcnow()
    if key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
        raise unauthorized("inactive_api_key", "The supplied API key is expired or revoked.")
    client = key.client
    if not client.active:
        raise unauthorized("inactive_client", "This API client is inactive.")
    key.last_used_at = now
    count, limit = _increment_rate_window(session, client, settings)
    session.commit()  # Quota consumption must survive a rejected application request.
    if count > limit:
        raise ApiProblemError(
            429,
            "rate_limit_exceeded",
            "Too many requests",
            "This API client has exceeded its per-minute request quota.",
            headers={"Retry-After": "60"},
        )
    return Principal(
        actor=f"client:{client.id}",
        client_id=client.id,
        key_id=key.id,
        scopes=frozenset(key.scopes),
    )


def authenticate_admin(
    session: Session,
    settings: Settings,
    authorization: str | None,
    api_key: str | None,
) -> Principal:
    if settings.bootstrap_admin_enabled and authorization and authorization.startswith("Bearer "):
        candidate = authorization.removeprefix("Bearer ")
        expected = settings.bootstrap_admin_token.get_secret_value()
        if hmac.compare_digest(candidate, expected):
            return Principal(
                actor="bootstrap-admin",
                client_id=None,
                key_id=None,
                scopes=frozenset({"admin"}),
                bootstrap=True,
            )
    principal = authenticate_api_key(session, settings, api_key)
    require_scope(principal, "admin")
    return principal


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes and "admin" not in principal.scopes:
        raise forbidden("insufficient_scope", f"This operation requires the {scope} scope.")


def issue_api_key(
    session: Session, settings: Settings, client: ApiClient, request: ApiKeyCreate
) -> tuple[ApiKey, str]:
    generated = generate_api_key(settings.api_key_pepper.get_secret_value())
    key = ApiKey(
        client_id=client.id,
        name=request.name,
        key_prefix=generated.prefix,
        secret_digest=generated.digest,
        scopes=sorted(request.scopes),
        expires_at=request.expires_at,
    )
    session.add(key)
    session.flush()
    return key, generated.plaintext
