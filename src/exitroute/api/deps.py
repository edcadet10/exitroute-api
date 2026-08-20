"""Request-scoped database, configuration, and authorization dependencies."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, cast

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from exitroute.config import Settings
from exitroute.services.auth import (
    Principal,
    authenticate_admin,
    authenticate_api_key,
    require_scope,
)

api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="A scoped key created by an ExitRoute administrator.",
    auto_error=False,
)
bootstrap_bearer_scheme = HTTPBearer(
    scheme_name="BootstrapAdminAuth",
    description="Bootstrap-only bearer token. Prefer a scoped admin API key after setup.",
    auto_error=False,
)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_session(request: Request) -> Generator[Session, None, None]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def api_principal(
    session: SessionDep,
    settings: SettingsDep,
    api_key: Annotated[str | None, Security(api_key_scheme)] = None,
) -> Principal:
    return authenticate_api_key(session, settings, api_key)


def route_reader(principal: Annotated[Principal, Depends(api_principal)]) -> Principal:
    require_scope(principal, "routes:read")
    return principal


def observation_writer(principal: Annotated[Principal, Depends(api_principal)]) -> Principal:
    require_scope(principal, "observations:write")
    return principal


def webhook_manager(principal: Annotated[Principal, Depends(api_principal)]) -> Principal:
    require_scope(principal, "webhooks:manage")
    return principal


def admin_principal(
    session: SessionDep,
    settings: SettingsDep,
    bearer: Annotated[
        HTTPAuthorizationCredentials | None, Security(bootstrap_bearer_scheme)
    ] = None,
    api_key: Annotated[str | None, Security(api_key_scheme)] = None,
) -> Principal:
    authorization = f"{bearer.scheme} {bearer.credentials}" if bearer else None
    return authenticate_admin(session, settings, authorization, api_key)


RouteReader = Annotated[Principal, Depends(route_reader)]
ObservationWriter = Annotated[Principal, Depends(observation_writer)]
WebhookManager = Annotated[Principal, Depends(webhook_manager)]
AdminPrincipal = Annotated[Principal, Depends(admin_principal)]
