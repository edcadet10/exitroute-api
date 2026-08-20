"""API-key protected catalog, route history, and change-feed endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, Response
from sqlalchemy import select

from exitroute.api.deps import RouteReader, SessionDep, SettingsDep
from exitroute.domain.graph import Platform, PublicationState, Slug, representation_etag
from exitroute.domain.security import InvalidCursorError, decode_cursor, encode_cursor
from exitroute.errors import bad_request, not_found
from exitroute.models import ChangeEvent, Route, RouteRevision, Service
from exitroute.schemas import (
    ChangePage,
    ExitRouteView,
    RevisionPage,
    RevisionSummary,
    ServicePage,
    ServiceView,
)
from exitroute.services.auth import Principal
from exitroute.services.routes import (
    build_exit_route_view,
    change_event_view,
    find_current_route,
    mark_revision_stale,
)

router = APIRouter(prefix="/v1", tags=["routes"])


def _cursor_payload(cursor: str | None, settings: SettingsDep, kind: str) -> dict[str, Any]:
    if cursor is None:
        return {}
    try:
        payload = decode_cursor(settings.cursor_secret.get_secret_value(), cursor)
    except InvalidCursorError as exc:
        raise bad_request("invalid_cursor", str(exc)) from exc
    if payload.get("kind") != kind:
        raise bad_request("cursor_scope_mismatch", "This cursor belongs to another collection.")
    return payload


def _next_cursor(settings: SettingsDep, payload: dict[str, Any]) -> str:
    return encode_cursor(
        settings.cursor_secret.get_secret_value(), payload, settings.cursor_ttl_seconds
    )


@router.get("/services", operation_id="listServices", response_model=ServicePage)
def list_services(
    session: SessionDep,
    settings: SettingsDep,
    _principal: RouteReader,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ServicePage:
    payload = _cursor_payload(cursor, settings, "services")
    after = payload.get("after", "")
    records = list(
        session.scalars(
            select(Service)
            .where(Service.active.is_(True), Service.slug > after)
            .order_by(Service.slug)
            .limit(limit + 1)
        )
    )
    has_more = len(records) > limit
    records = records[:limit]
    next_cursor = (
        _next_cursor(settings, {"kind": "services", "after": records[-1].slug})
        if has_more and records
        else None
    )
    return ServicePage(
        data=[ServiceView.model_validate(record) for record in records], next_cursor=next_cursor
    )


def _serve_revision(
    session: SessionDep,
    service: Service,
    route: Route,
    revision: RouteRevision,
    if_none_match: str | None,
) -> Response | ExitRouteView:
    etag = representation_etag(
        revision.fingerprint,
        revision.publication_state,
        revision.trust_state,
        revision.status_version,
    )
    headers = {"ETag": etag, "Cache-Control": "private, max-age=60, must-revalidate"}
    candidates = [
        candidate.strip().removeprefix("W/") for candidate in (if_none_match or "").split(",")
    ]
    if "*" in candidates or etag in candidates:
        return Response(status_code=304, headers=headers)
    view = build_exit_route_view(session, service, route, revision)
    return Response(
        content=view.model_dump_json(),
        status_code=200,
        media_type="application/json",
        headers=headers,
    )


@router.get(
    "/services/{service_slug}/exit-route",
    operation_id="getCurrentExitRoute",
    response_model=ExitRouteView,
    responses={304: {"description": "The cached representation is current."}},
)
def get_current_exit_route(
    service_slug: Slug,
    session: SessionDep,
    _principal: RouteReader,
    region: Annotated[str, Query(pattern=r"^[A-Z]{2}$")] = "US",
    platform: Platform = Platform.WEB,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response | ExitRouteView:
    service, route, revision = find_current_route(session, service_slug, region, platform.value)
    if (
        revision.trust_state == "verified"
        and revision.review_due_at is not None
        and revision.review_due_at <= datetime.now(UTC)
    ):
        system = Principal(
            actor="system:read-freshness",
            client_id=None,
            key_id=None,
            scopes=frozenset({"admin"}),
        )
        mark_revision_stale(session, revision.id, system, None)
    return _serve_revision(session, service, route, revision, if_none_match)


@router.get(
    "/services/{service_slug}/exit-route/revisions",
    operation_id="listExitRouteRevisions",
    response_model=RevisionPage,
)
def list_revisions(
    service_slug: Slug,
    session: SessionDep,
    settings: SettingsDep,
    _principal: RouteReader,
    region: Annotated[str, Query(pattern=r"^[A-Z]{2}$")] = "US",
    platform: Platform = Platform.WEB,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> RevisionPage:
    route = session.scalar(
        select(Route)
        .join(Service, Service.id == Route.service_id)
        .where(
            Service.slug == service_slug,
            Route.region == region,
            Route.platform == platform.value,
            Route.outcome == "cancel_subscription",
        )
    )
    if route is None:
        raise not_found("route_not_found", "No route exists for this service variant.")
    payload = _cursor_payload(cursor, settings, "revisions")
    if payload and payload.get("route_id") != str(route.id):
        raise bad_request("cursor_scope_mismatch", "This cursor belongs to another route.")
    before = int(payload.get("before", 2**31 - 1))
    records = list(
        session.scalars(
            select(RouteRevision)
            .where(
                RouteRevision.route_id == route.id,
                RouteRevision.revision < before,
                RouteRevision.publication_state.in_(
                    [PublicationState.PUBLISHED.value, PublicationState.SUPERSEDED.value]
                ),
            )
            .order_by(RouteRevision.revision.desc())
            .limit(limit + 1)
        )
    )
    has_more = len(records) > limit
    records = records[:limit]
    next_cursor = (
        _next_cursor(
            settings,
            {"kind": "revisions", "route_id": str(route.id), "before": records[-1].revision},
        )
        if has_more and records
        else None
    )
    return RevisionPage(
        data=[
            RevisionSummary(
                id=record.id,
                revision=record.revision,
                publication_state=record.publication_state,
                status=record.trust_state,
                verified_at=record.verified_at,
                review_due_at=record.review_due_at,
                fingerprint=record.fingerprint,
                change_summary=record.change_summary,
            )
            for record in records
        ],
        next_cursor=next_cursor,
    )


@router.get(
    "/services/{service_slug}/exit-route/revisions/{revision_number}",
    operation_id="getExitRouteRevision",
    response_model=ExitRouteView,
    responses={304: {"description": "The cached representation is current."}},
)
def get_revision(
    service_slug: Slug,
    revision_number: Annotated[int, Path(ge=1)],
    session: SessionDep,
    _principal: RouteReader,
    region: Annotated[str, Query(pattern=r"^[A-Z]{2}$")] = "US",
    platform: Platform = Platform.WEB,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response | ExitRouteView:
    record = session.execute(
        select(Service, Route, RouteRevision)
        .join(Route, Route.service_id == Service.id)
        .join(RouteRevision, RouteRevision.route_id == Route.id)
        .where(
            Service.slug == service_slug,
            Route.region == region,
            Route.platform == platform.value,
            Route.outcome == "cancel_subscription",
            RouteRevision.revision == revision_number,
            RouteRevision.publication_state.in_(
                [PublicationState.PUBLISHED.value, PublicationState.SUPERSEDED.value]
            ),
        )
    ).one_or_none()
    if record is None:
        raise not_found("revision_not_found", "No public revision matches this request.")
    service, route, revision = record._tuple()
    return _serve_revision(session, service, route, revision, if_none_match)


@router.get("/changes", operation_id="listRouteChanges", response_model=ChangePage)
def list_changes(
    session: SessionDep,
    settings: SettingsDep,
    _principal: RouteReader,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ChangePage:
    payload = _cursor_payload(cursor, settings, "changes")
    after = int(payload.get("after", 0))
    records = list(
        session.scalars(
            select(ChangeEvent)
            .where(ChangeEvent.sequence > after)
            .order_by(ChangeEvent.sequence)
            .limit(limit + 1)
        )
    )
    has_more = len(records) > limit
    records = records[:limit]
    next_cursor = (
        _next_cursor(settings, {"kind": "changes", "after": records[-1].sequence})
        if has_more and records
        else None
    )
    return ChangePage(
        data=[change_event_view(session, event) for event in records], next_cursor=next_cursor
    )
