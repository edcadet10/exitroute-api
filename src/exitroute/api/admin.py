"""Authenticated editorial and credential-management endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import and_, or_, select

from exitroute.api.deps import AdminPrincipal, SessionDep, SettingsDep
from exitroute.domain.security import InvalidCursorError, decode_cursor, encode_cursor
from exitroute.errors import bad_request, conflict, not_found
from exitroute.models import ApiClient, ApiKey, Observation
from exitroute.schemas import (
    ApiClientCreate,
    ApiClientView,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyView,
    ObservationAdminPage,
    ObservationAdminView,
    ObservationModerate,
    PublishRevision,
    RevisionCreate,
    RevisionDraftView,
    RevisionStateView,
    RouteCreate,
    RouteView,
    ServiceCreate,
    ServiceView,
    VerificationCreate,
    VerificationView,
)
from exitroute.services.auth import audit, issue_api_key
from exitroute.services.routes import (
    add_verification,
    create_revision,
    create_route,
    create_service,
    mark_revision_stale,
    publish_revision,
    withdraw_revision,
)

router = APIRouter(prefix="/admin/v1", tags=["admin"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post(
    "/services",
    operation_id="adminCreateService",
    response_model=ServiceView,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_service(
    body: ServiceCreate,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> ServiceView:
    return ServiceView.model_validate(
        create_service(session, body, principal, _request_id(request))
    )


@router.post(
    "/routes",
    operation_id="adminCreateRoute",
    response_model=RouteView,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_route(
    body: RouteCreate,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> RouteView:
    return RouteView.model_validate(create_route(session, body, principal, _request_id(request)))


@router.post(
    "/revisions",
    operation_id="adminCreateRevision",
    response_model=RevisionDraftView,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_revision(
    body: RevisionCreate,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> RevisionDraftView:
    revision = create_revision(session, body, principal, _request_id(request))
    return RevisionDraftView.model_validate(revision)


@router.post(
    "/revisions/{revision_id}/verifications",
    operation_id="adminVerifyRevision",
    response_model=VerificationView,
    status_code=status.HTTP_201_CREATED,
)
def admin_verify_revision(
    revision_id: uuid.UUID,
    body: VerificationCreate,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> VerificationView:
    return VerificationView.model_validate(
        add_verification(session, revision_id, body, principal, _request_id(request))
    )


@router.post(
    "/revisions/{revision_id}/publish",
    operation_id="adminPublishRevision",
    response_model=RevisionStateView,
)
def admin_publish_revision(
    revision_id: uuid.UUID,
    body: PublishRevision,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    principal: AdminPrincipal,
) -> RevisionStateView:
    revision = publish_revision(
        session,
        revision_id,
        body.review_due_at,
        settings,
        principal,
        _request_id(request),
    )
    return RevisionStateView.model_validate(revision)


@router.post(
    "/revisions/{revision_id}/mark-stale",
    operation_id="adminMarkRevisionStale",
    response_model=RevisionStateView,
)
def admin_mark_stale(
    revision_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> RevisionStateView:
    revision = mark_revision_stale(
        session, revision_id, principal, _request_id(request), summary="Marked stale by an editor."
    )
    return RevisionStateView.model_validate(revision)


@router.post(
    "/revisions/{revision_id}/withdraw",
    operation_id="adminWithdrawRevision",
    response_model=RevisionStateView,
)
def admin_withdraw_revision(
    revision_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> RevisionStateView:
    revision = withdraw_revision(session, revision_id, principal, _request_id(request))
    return RevisionStateView.model_validate(revision)


@router.post(
    "/api-clients",
    operation_id="adminCreateApiClient",
    response_model=ApiClientView,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_client(
    body: ApiClientCreate,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> ApiClientView:
    client = ApiClient(name=body.name.strip(), rate_limit_per_minute=body.rate_limit_per_minute)
    session.add(client)
    session.flush()
    audit(
        session,
        principal,
        "api_client.created",
        "api_client",
        str(client.id),
        request_id=_request_id(request),
    )
    return ApiClientView.model_validate(client)


@router.post(
    "/api-clients/{client_id}/keys",
    operation_id="adminCreateApiKey",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_key(
    client_id: uuid.UUID,
    body: ApiKeyCreate,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    principal: AdminPrincipal,
) -> ApiKeyCreated:
    client = session.get(ApiClient, client_id)
    if client is None:
        raise not_found("client_not_found", "The requested API client does not exist.")
    if not client.active:
        raise conflict("client_inactive", "Keys cannot be created for an inactive client.")
    key, plaintext = issue_api_key(session, settings, client, body)
    audit(
        session,
        principal,
        "api_key.created",
        "api_key",
        str(key.id),
        request_id=_request_id(request),
        context={"scopes": key.scopes},
    )
    return ApiKeyCreated(
        id=key.id,
        client_id=key.client_id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=key.scopes,
        expires_at=key.expires_at,
        plaintext_key=plaintext,
    )


@router.get(
    "/api-clients/{client_id}/keys",
    operation_id="adminListApiKeys",
    response_model=list[ApiKeyView],
)
def admin_list_keys(
    client_id: uuid.UUID,
    session: SessionDep,
    _principal: AdminPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[ApiKeyView]:
    if session.get(ApiClient, client_id) is None:
        raise not_found("client_not_found", "The requested API client does not exist.")
    keys = session.scalars(
        select(ApiKey)
        .where(ApiKey.client_id == client_id)
        .order_by(ApiKey.created_at.desc())
        .limit(limit)
    )
    return [ApiKeyView.model_validate(key) for key in keys]


@router.post(
    "/api-keys/{key_id}/rotate",
    operation_id="adminRotateApiKey",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
def admin_rotate_key(
    key_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    principal: AdminPrincipal,
) -> ApiKeyCreated:
    old = session.scalar(select(ApiKey).where(ApiKey.id == key_id).with_for_update())
    if old is None:
        raise not_found("api_key_not_found", "The requested API key does not exist.")
    if old.revoked_at is not None:
        raise conflict("api_key_revoked", "A revoked key cannot be rotated.")
    client = session.get(ApiClient, old.client_id)
    assert client is not None
    body = ApiKeyCreate(
        name=f"{old.name} (rotated)", scopes=set(old.scopes), expires_at=old.expires_at
    )
    new, plaintext = issue_api_key(session, settings, client, body)
    old.revoked_at = datetime.now(UTC)
    audit(
        session,
        principal,
        "api_key.rotated",
        "api_key",
        str(old.id),
        request_id=_request_id(request),
        context={"replacement_id": str(new.id)},
    )
    return ApiKeyCreated(
        id=new.id,
        client_id=new.client_id,
        name=new.name,
        key_prefix=new.key_prefix,
        scopes=new.scopes,
        expires_at=new.expires_at,
        plaintext_key=plaintext,
    )


@router.delete(
    "/api-keys/{key_id}",
    operation_id="adminRevokeApiKey",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_revoke_key(
    key_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> None:
    key = session.scalar(select(ApiKey).where(ApiKey.id == key_id).with_for_update())
    if key is None:
        raise not_found("api_key_not_found", "The requested API key does not exist.")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        audit(
            session,
            principal,
            "api_key.revoked",
            "api_key",
            str(key.id),
            request_id=_request_id(request),
        )


@router.delete(
    "/api-clients/{client_id}",
    operation_id="adminDeactivateApiClient",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_deactivate_client(
    client_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> None:
    client = session.scalar(select(ApiClient).where(ApiClient.id == client_id).with_for_update())
    if client is None:
        raise not_found("client_not_found", "The requested API client does not exist.")
    client.active = False
    now = datetime.now(UTC)
    for key in session.scalars(select(ApiKey).where(ApiKey.client_id == client.id)):
        key.revoked_at = key.revoked_at or now
    audit(
        session,
        principal,
        "api_client.deactivated",
        "api_client",
        str(client.id),
        request_id=_request_id(request),
    )


@router.get(
    "/observations",
    operation_id="adminListObservations",
    response_model=ObservationAdminPage,
)
def admin_list_observations(
    session: SessionDep,
    settings: SettingsDep,
    _principal: AdminPrincipal,
    moderation_state: Literal["queued", "accepted", "rejected"] = "queued",
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ObservationAdminPage:
    before_at: datetime | None = None
    before_id: uuid.UUID | None = None
    if cursor:
        try:
            payload = decode_cursor(settings.cursor_secret.get_secret_value(), cursor)
            if (
                payload.get("kind") != "admin_observations"
                or payload.get("moderation_state") != moderation_state
            ):
                raise InvalidCursorError("cursor belongs to another observation queue")
            before_at = datetime.fromisoformat(str(payload["before_at"]))
            before_id = uuid.UUID(str(payload["before_id"]))
        except (InvalidCursorError, KeyError, ValueError) as exc:
            raise bad_request("invalid_cursor", str(exc)) from exc
    statement = select(Observation).where(Observation.moderation_state == moderation_state)
    if before_at is not None and before_id is not None:
        statement = statement.where(
            or_(
                Observation.received_at < before_at,
                and_(Observation.received_at == before_at, Observation.id < before_id),
            )
        )
    records = list(
        session.scalars(
            statement.order_by(Observation.received_at.desc(), Observation.id.desc()).limit(
                limit + 1
            )
        )
    )
    has_more = len(records) > limit
    records = records[:limit]
    next_cursor = None
    if has_more and records:
        last = records[-1]
        next_cursor = encode_cursor(
            settings.cursor_secret.get_secret_value(),
            {
                "kind": "admin_observations",
                "moderation_state": moderation_state,
                "before_at": last.received_at.isoformat(),
                "before_id": str(last.id),
            },
            settings.cursor_ttl_seconds,
        )
    return ObservationAdminPage(
        data=[ObservationAdminView.model_validate(record) for record in records],
        next_cursor=next_cursor,
    )


@router.post(
    "/observations/{observation_id}/moderate",
    operation_id="adminModerateObservation",
    response_model=ObservationAdminView,
)
def admin_moderate_observation(
    observation_id: uuid.UUID,
    body: ObservationModerate,
    request: Request,
    session: SessionDep,
    principal: AdminPrincipal,
) -> ObservationAdminView:
    observation = session.scalar(
        select(Observation).where(Observation.id == observation_id).with_for_update()
    )
    if observation is None:
        raise not_found("observation_not_found", "The requested observation does not exist.")
    if observation.moderation_state != "queued":
        raise conflict("observation_already_moderated", "This observation is already moderated.")
    observation.moderation_state = body.moderation_state
    observation.moderated_at = datetime.now(UTC)
    observation.moderated_by = principal.actor
    observation.decision_reason = body.decision_reason.strip()
    audit(
        session,
        principal,
        "observation.moderated",
        "observation",
        str(observation.id),
        request_id=_request_id(request),
        context={"moderation_state": body.moderation_state},
    )
    return ObservationAdminView.model_validate(observation)
