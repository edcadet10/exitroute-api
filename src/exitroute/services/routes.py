"""Editorial state machine and public route projections."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

from pydantic import HttpUrl
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from exitroute.config import Settings
from exitroute.domain.graph import (
    PublicationState,
    RouteGraph,
    TrustState,
    analyze_graph,
    content_fingerprint,
)
from exitroute.errors import conflict, not_found, unprocessable
from exitroute.models import (
    ChangeEvent,
    Route,
    RouteRevision,
    Service,
    VerificationEvent,
    WebhookDelivery,
    WebhookSubscription,
)
from exitroute.schemas import (
    ChangeEventView,
    EvidenceSummary,
    ExitRouteView,
    RevisionCreate,
    RouteCreate,
    ServiceCreate,
    ServiceRef,
    Variant,
    VerificationCreate,
)
from exitroute.services.auth import Principal, audit, utcnow

_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise unprocessable("timezone_required", f"{field} must include a UTC offset.")


def create_service(
    session: Session,
    request: ServiceCreate,
    principal: Principal,
    request_id: str | None,
) -> Service:
    domains = sorted({domain.lower().rstrip(".") for domain in request.domains})
    if any(not _DOMAIN.fullmatch(domain) for domain in domains):
        raise unprocessable("invalid_domain", "domains must contain DNS names without URLs.")
    service = Service(slug=request.slug, name=request.name.strip(), domains=domains)
    session.add(service)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict("service_exists", "A service with this slug already exists.") from exc
    audit(session, principal, "service.created", "service", str(service.id), request_id=request_id)
    return service


def create_route(
    session: Session,
    request: RouteCreate,
    principal: Principal,
    request_id: str | None,
) -> Route:
    service = session.scalar(select(Service).where(Service.slug == request.service_slug))
    if service is None:
        raise not_found("service_not_found", "The requested service does not exist.")
    route = Route(
        service_id=service.id,
        outcome=request.outcome.value,
        region=request.variant.region,
        platform=request.variant.platform.value,
    )
    session.add(route)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict("route_exists", "This service variant already has a route.") from exc
    audit(session, principal, "route.created", "route", str(route.id), request_id=request_id)
    return route


def create_revision(
    session: Session,
    request: RevisionCreate,
    principal: Principal,
    request_id: str | None,
) -> RouteRevision:
    route = session.scalar(select(Route).where(Route.id == request.route_id).with_for_update())
    if route is None:
        raise not_found("route_not_found", "The requested route does not exist.")
    if request.entry_url.scheme != "https":
        raise unprocessable("insecure_entry_url", "entry_url must use HTTPS.")
    try:
        computed = analyze_graph(request.graph)
    except ValueError as exc:
        raise unprocessable("invalid_route_graph", str(exc)) from exc
    fingerprint = content_fingerprint(request.entry_url, request.graph, computed)
    next_revision = (
        session.scalar(
            select(func.coalesce(func.max(RouteRevision.revision), 0)).where(
                RouteRevision.route_id == route.id
            )
        )
        or 0
    ) + 1
    revision = RouteRevision(
        route_id=route.id,
        revision=next_revision,
        publication_state=PublicationState.DRAFT.value,
        trust_state=TrustState.PROVISIONAL.value,
        entry_url=str(request.entry_url),
        graph=request.graph.model_dump(mode="json"),
        best_route=computed.best_route,
        friction=computed.friction.model_dump(mode="json"),
        algorithm_version=computed.friction.algorithm_version,
        fingerprint=fingerprint,
        confidence=request.confidence.value,
        change_summary=request.change_summary.strip(),
    )
    session.add(revision)
    try:
        session.flush()
    except IntegrityError as exc:
        raise conflict(
            "duplicate_revision_content", "An identical route revision already exists."
        ) from exc
    audit(
        session,
        principal,
        "revision.created",
        "route_revision",
        str(revision.id),
        request_id=request_id,
        context={"revision": revision.revision},
    )
    return revision


def add_verification(
    session: Session,
    revision_id: uuid.UUID,
    request: VerificationCreate,
    principal: Principal,
    request_id: str | None,
) -> VerificationEvent:
    _require_aware(request.occurred_at, "occurred_at")
    now = utcnow()
    if request.occurred_at > now + timedelta(minutes=5):
        raise unprocessable("future_verification", "occurred_at is too far in the future.")
    revision = session.get(RouteRevision, revision_id)
    if revision is None:
        raise not_found("revision_not_found", "The requested revision does not exist.")
    if revision.publication_state != PublicationState.DRAFT.value:
        raise conflict("revision_locked", "Only draft revisions can receive verification events.")
    event = VerificationEvent(
        revision_id=revision.id,
        verifier=request.verifier.strip(),
        environment=request.environment.strip(),
        result=request.result,
        evidence_ref=request.evidence_ref,
        notes=request.notes,
        occurred_at=request.occurred_at,
    )
    session.add(event)
    session.flush()
    audit(
        session,
        principal,
        "verification.recorded",
        "route_revision",
        str(revision.id),
        request_id=request_id,
        context={"result": request.result},
    )
    return event


def _event_payload(
    event: ChangeEvent, service: Service, route: Route, revision: RouteRevision
) -> dict[str, object]:
    return {
        "id": str(event.id),
        "type": f"route.{event.event_type}",
        "occurred_at": event.occurred_at.isoformat(),
        "data": {
            "service": {"slug": service.slug, "name": service.name},
            "variant": {"region": route.region, "platform": route.platform},
            "outcome": route.outcome,
            "revision": revision.revision,
            "fingerprint": revision.fingerprint,
            "status": revision.trust_state,
            "summary": event.summary,
        },
    }


def emit_change(
    session: Session,
    route: Route,
    revision: RouteRevision,
    event_type: str,
    summary: str,
) -> ChangeEvent:
    service = session.get(Service, route.service_id)
    assert service is not None
    event = ChangeEvent(
        route_id=route.id,
        revision_id=revision.id,
        event_type=event_type,
        summary=summary,
        occurred_at=utcnow(),
    )
    session.add(event)
    session.flush()
    payload = _event_payload(event, service, route, revision)
    subscriptions = session.scalars(
        select(WebhookSubscription).where(WebhookSubscription.active.is_(True))
    )
    for subscription in subscriptions:
        if event_type in subscription.event_types:
            session.add(
                WebhookDelivery(
                    subscription_id=subscription.id,
                    event_id=event.id,
                    payload=payload,
                    next_attempt_at=utcnow(),
                )
            )
    return event


def publish_revision(
    session: Session,
    revision_id: uuid.UUID,
    review_due_at: datetime,
    settings: Settings,
    principal: Principal,
    request_id: str | None,
) -> RouteRevision:
    _require_aware(review_due_at, "review_due_at")
    revision = session.scalar(
        select(RouteRevision).where(RouteRevision.id == revision_id).with_for_update()
    )
    if revision is None:
        raise not_found("revision_not_found", "The requested revision does not exist.")
    if revision.publication_state != PublicationState.DRAFT.value:
        raise conflict("revision_not_draft", "Only a draft revision can be published.")
    events = list(
        session.scalars(
            select(VerificationEvent).where(
                VerificationEvent.revision_id == revision.id,
                VerificationEvent.result == "passed",
            )
        )
    )
    verifiers = {event.verifier.casefold() for event in events}
    environments = {event.environment.casefold() for event in events}
    if len(events) < 2 or len(verifiers) < 2 or len(environments) < 2:
        raise conflict(
            "verification_insufficient",
            "Publishing requires two successful sessions with distinct verifiers and environments.",
        )
    verified_at = max(event.occurred_at for event in events)
    now = utcnow()
    if review_due_at <= verified_at or review_due_at <= now:
        raise unprocessable(
            "invalid_review_due_at", "review_due_at must be later than verification and now."
        )
    max_due = now + timedelta(days=settings.review_window_days)
    if review_due_at > max_due:
        raise unprocessable(
            "review_window_exceeded",
            f"review_due_at cannot be more than {settings.review_window_days} days away.",
        )
    route = session.scalar(select(Route).where(Route.id == revision.route_id).with_for_update())
    assert route is not None
    if route.current_revision_id is not None:
        previous = session.get(RouteRevision, route.current_revision_id)
        if previous is not None:
            previous.publication_state = PublicationState.SUPERSEDED.value
            previous.status_version += 1
            emit_change(
                session,
                route,
                previous,
                "superseded",
                f"Superseded by revision {revision.revision}.",
            )
    revision.publication_state = PublicationState.PUBLISHED.value
    revision.trust_state = TrustState.VERIFIED.value
    revision.status_version += 1
    revision.verified_at = verified_at
    revision.review_due_at = review_due_at
    revision.published_at = now
    route.current_revision_id = revision.id
    emit_change(session, route, revision, "published", revision.change_summary)
    audit(
        session,
        principal,
        "revision.published",
        "route_revision",
        str(revision.id),
        request_id=request_id,
        context={"revision": revision.revision},
    )
    return revision


def mark_revision_stale(
    session: Session,
    revision_id: uuid.UUID,
    principal: Principal,
    request_id: str | None,
    *,
    summary: str = "The verification review window elapsed.",
) -> RouteRevision:
    revision = session.scalar(
        select(RouteRevision).where(RouteRevision.id == revision_id).with_for_update()
    )
    if revision is None:
        raise not_found("revision_not_found", "The requested revision does not exist.")
    if revision.publication_state != PublicationState.PUBLISHED.value:
        raise conflict("revision_not_current", "Only a published revision can be marked stale.")
    if revision.trust_state == TrustState.STALE.value:
        return revision
    route = session.get(Route, revision.route_id)
    assert route is not None
    revision.trust_state = TrustState.STALE.value
    revision.status_version += 1
    emit_change(session, route, revision, "stale", summary)
    audit(
        session,
        principal,
        "revision.marked_stale",
        "route_revision",
        str(revision.id),
        request_id=request_id,
    )
    return revision


def withdraw_revision(
    session: Session,
    revision_id: uuid.UUID,
    principal: Principal,
    request_id: str | None,
) -> RouteRevision:
    revision = session.scalar(
        select(RouteRevision).where(RouteRevision.id == revision_id).with_for_update()
    )
    if revision is None:
        raise not_found("revision_not_found", "The requested revision does not exist.")
    if revision.publication_state != PublicationState.PUBLISHED.value:
        raise conflict("revision_not_current", "Only a published revision can be withdrawn.")
    route = session.scalar(select(Route).where(Route.id == revision.route_id).with_for_update())
    assert route is not None
    revision.publication_state = PublicationState.WITHDRAWN.value
    revision.status_version += 1
    if route.current_revision_id == revision.id:
        route.current_revision_id = None
    emit_change(session, route, revision, "withdrawn", "Route withdrawn by an editor.")
    audit(
        session,
        principal,
        "revision.withdrawn",
        "route_revision",
        str(revision.id),
        request_id=request_id,
    )
    return revision


def current_route_statement(
    slug: str, region: str, platform: str
) -> Select[tuple[Service, Route, RouteRevision]]:
    return (
        select(Service, Route, RouteRevision)
        .join(Route, Route.service_id == Service.id)
        .join(RouteRevision, RouteRevision.id == Route.current_revision_id)
        .where(
            Service.slug == slug,
            Service.active.is_(True),
            Route.region == region,
            Route.platform == platform,
            Route.outcome == "cancel_subscription",
            RouteRevision.publication_state == PublicationState.PUBLISHED.value,
        )
    )


def find_current_route(
    session: Session, slug: str, region: str, platform: str
) -> tuple[Service, Route, RouteRevision]:
    record = session.execute(current_route_statement(slug, region, platform)).one_or_none()
    if record is None:
        raise not_found("route_not_found", "No current route exists for this service variant.")
    return record._tuple()


def build_exit_route_view(
    session: Session, service: Service, route: Route, revision: RouteRevision
) -> ExitRouteView:
    passed = session.scalar(
        select(func.count())
        .select_from(VerificationEvent)
        .where(
            VerificationEvent.revision_id == revision.id,
            VerificationEvent.result == "passed",
        )
    )
    assert revision.verified_at is not None
    assert revision.review_due_at is not None
    return ExitRouteView(
        id=revision.id,
        service=ServiceRef(slug=service.slug, name=service.name),
        outcome=route.outcome,
        variant=Variant(region=route.region, platform=route.platform),
        revision=revision.revision,
        publication_state=revision.publication_state,
        status=revision.trust_state,
        verified_at=revision.verified_at,
        review_due_at=revision.review_due_at,
        entry_url=HttpUrl(revision.entry_url),
        graph=RouteGraph.model_validate(revision.graph),
        best_route=revision.best_route,
        friction=revision.friction,
        confidence=revision.confidence,
        evidence_summary=EvidenceSummary(
            verification_sessions=passed or 0,
            change_summary=revision.change_summary,
        ),
        fingerprint=revision.fingerprint,
    )


def change_event_view(session: Session, event: ChangeEvent) -> ChangeEventView:
    route = session.get(Route, event.route_id)
    revision = session.get(RouteRevision, event.revision_id)
    assert route is not None
    assert revision is not None
    service = session.get(Service, route.service_id)
    assert service is not None
    return ChangeEventView(
        id=event.id,
        occurred_at=event.occurred_at,
        service=ServiceRef(slug=service.slug, name=service.name),
        variant=Variant(region=route.region, platform=route.platform),
        revision=revision.revision,
        event_type=event.event_type,
        summary=event.summary,
    )
