"""Structured, idempotent, moderation-only change reports."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Header, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from exitroute.api.deps import ObservationWriter, SessionDep
from exitroute.errors import conflict, not_found, unprocessable
from exitroute.models import Observation, Route, Service
from exitroute.schemas import ObservationCreate, ObservationReceipt
from exitroute.services.auth import utcnow

router = APIRouter(prefix="/v1", tags=["observations"])


def _canonical_payload(body: ObservationCreate) -> tuple[dict[str, object], str]:
    payload = body.model_dump(mode="json")
    payload["change_types"] = sorted(body.change_types)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return payload, hashlib.sha256(encoded).hexdigest()


@router.post(
    "/observations",
    operation_id="createObservation",
    response_model=ObservationReceipt,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_observation(
    body: ObservationCreate,
    session: SessionDep,
    principal: ObservationWriter,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> ObservationReceipt:
    assert principal.client_id is not None
    if body.occurred_at.tzinfo is None or body.occurred_at.utcoffset() is None:
        raise unprocessable("timezone_required", "occurred_at must include a UTC offset.")
    now = utcnow()
    if not now - timedelta(days=90) <= body.occurred_at <= now + timedelta(minutes=5):
        raise unprocessable(
            "observation_time_out_of_range",
            "occurred_at must be within the last 90 days and no more than 5 minutes ahead.",
        )
    route = session.scalar(
        select(Route)
        .join(Service, Service.id == Route.service_id)
        .where(
            Service.slug == body.service_slug,
            Route.outcome == body.outcome.value,
            Route.region == body.variant.region,
            Route.platform == body.variant.platform.value,
        )
    )
    if route is None:
        raise not_found("route_not_found", "The observation does not match a known route variant.")
    payload, payload_hash = _canonical_payload(body)
    existing = session.scalar(
        select(Observation).where(
            Observation.client_id == principal.client_id,
            Observation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise conflict(
                "idempotency_key_reused",
                "The same Idempotency-Key was already used with a different payload.",
            )
        return ObservationReceipt(
            id=existing.id,
            moderation_state=existing.moderation_state,
            duplicate=True,
            received_at=existing.received_at,
        )
    observation = Observation(
        client_id=principal.client_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        payload=payload,
    )
    try:
        with session.begin_nested():
            session.add(observation)
            session.flush()
    except IntegrityError as exc:
        existing = session.scalar(
            select(Observation).where(
                Observation.client_id == principal.client_id,
                Observation.idempotency_key == idempotency_key,
            )
        )
        if existing is None or existing.payload_hash != payload_hash:
            raise conflict(
                "idempotency_key_reused",
                "The same Idempotency-Key was concurrently used with another payload.",
            ) from exc
        return ObservationReceipt(
            id=existing.id,
            moderation_state=existing.moderation_state,
            duplicate=True,
            received_at=existing.received_at,
        )
    return ObservationReceipt(
        id=observation.id,
        duplicate=False,
        received_at=observation.received_at,
    )
