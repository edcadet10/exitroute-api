"""Typed HTTP request and response contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from exitroute.domain.graph import (
    Confidence,
    Friction,
    Outcome,
    Platform,
    PublicationState,
    RouteGraph,
    Slug,
    TrustState,
)
from exitroute.domain.security import contains_sensitive_text


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Problem(ApiModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    instance: str | None = None
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class Health(ApiModel):
    status: Literal["ok"] = "ok"


class Ready(ApiModel):
    status: Literal["ready"] = "ready"
    database: Literal["ok"] = "ok"


class ServiceCreate(ApiModel):
    slug: Slug
    name: Annotated[str, Field(min_length=1, max_length=120)]
    domains: list[str] = Field(default_factory=list, max_length=20)


class ServiceView(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    domains: list[str]
    active: bool
    created_at: datetime


class ServiceRef(ApiModel):
    slug: str
    name: str


class ServicePage(ApiModel):
    data: list[ServiceView]
    next_cursor: str | None


class Variant(ApiModel):
    region: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "US"
    platform: Platform = Platform.WEB


class RouteCreate(ApiModel):
    service_slug: Slug
    outcome: Outcome = Outcome.CANCEL_SUBSCRIPTION
    variant: Variant = Field(default_factory=Variant)


class RouteView(ApiModel):
    id: uuid.UUID
    service_id: uuid.UUID
    outcome: str
    region: str
    platform: str
    current_revision_id: uuid.UUID | None
    created_at: datetime


class RevisionCreate(ApiModel):
    route_id: uuid.UUID
    entry_url: HttpUrl
    graph: RouteGraph
    confidence: Confidence = Confidence.LOW
    change_summary: Annotated[str, Field(min_length=1, max_length=280)]


class RevisionDraftView(ApiModel):
    id: uuid.UUID
    route_id: uuid.UUID
    revision: int
    publication_state: PublicationState
    trust_state: TrustState
    fingerprint: str
    best_route: list[str]
    friction: Friction
    created_at: datetime


class VerificationCreate(ApiModel):
    verifier: Annotated[str, Field(min_length=2, max_length=120)]
    environment: Annotated[str, Field(min_length=2, max_length=280)]
    result: Literal["passed", "failed"]
    evidence_ref: Annotated[str | None, Field(max_length=500)] = None
    notes: Annotated[str | None, Field(max_length=500)] = None
    occurred_at: datetime


class VerificationView(ApiModel):
    id: uuid.UUID
    revision_id: uuid.UUID
    verifier: str
    environment: str
    result: str
    occurred_at: datetime


class PublishRevision(ApiModel):
    review_due_at: datetime


class RevisionStateView(ApiModel):
    id: uuid.UUID
    revision: int
    publication_state: PublicationState
    trust_state: TrustState
    status_version: int
    verified_at: datetime | None
    review_due_at: datetime | None
    published_at: datetime | None


class EvidenceSummary(ApiModel):
    method: Literal["manual_clean_session"] = "manual_clean_session"
    verification_sessions: int
    change_summary: str


class ExitRouteView(ApiModel):
    id: uuid.UUID
    service: ServiceRef
    outcome: Outcome
    variant: Variant
    revision: int
    publication_state: PublicationState
    status: TrustState
    verified_at: datetime
    review_due_at: datetime
    entry_url: HttpUrl
    graph: RouteGraph
    best_route: list[str]
    friction: Friction
    confidence: Confidence
    evidence_summary: EvidenceSummary
    fingerprint: str


class RevisionSummary(ApiModel):
    id: uuid.UUID
    revision: int
    publication_state: PublicationState
    status: TrustState
    verified_at: datetime | None
    review_due_at: datetime | None
    fingerprint: str
    change_summary: str


class RevisionPage(ApiModel):
    data: list[RevisionSummary]
    next_cursor: str | None


class ChangeEventView(ApiModel):
    id: uuid.UUID
    occurred_at: datetime
    service: ServiceRef
    variant: Variant
    revision: int
    event_type: Literal["published", "superseded", "stale", "withdrawn"]
    summary: str


class ChangePage(ApiModel):
    data: list[ChangeEventView]
    next_cursor: str | None


ChangeType = Literal[
    "entry_url_changed",
    "choice_label_changed",
    "step_added",
    "step_removed",
    "loop_added",
    "retention_offer_added",
    "offline_handoff_added",
    "cancellation_terminal_missing",
    "variant_mismatch",
    "other",
]


class ObservationCreate(ApiModel):
    service_slug: Slug
    observed_revision: Annotated[int | None, Field(ge=1)] = None
    outcome: Outcome = Outcome.CANCEL_SUBSCRIPTION
    variant: Variant = Field(default_factory=Variant)
    occurred_at: datetime
    change_types: Annotated[set[ChangeType], Field(min_length=1, max_length=10)]
    note: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def reject_sensitive_note(self) -> ObservationCreate:
        if contains_sensitive_text(self.note):
            raise ValueError("note appears to contain sensitive text, contact data, or a URL")
        return self


class ObservationReceipt(ApiModel):
    id: uuid.UUID
    moderation_state: Literal["queued", "accepted", "rejected"] = "queued"
    duplicate: bool
    received_at: datetime


class ObservationAdminView(ApiModel):
    id: uuid.UUID
    client_id: uuid.UUID
    payload: dict[str, Any]
    moderation_state: Literal["queued", "accepted", "rejected"]
    received_at: datetime
    moderated_at: datetime | None
    moderated_by: str | None
    decision_reason: str | None


class ObservationAdminPage(ApiModel):
    data: list[ObservationAdminView]
    next_cursor: str | None


class ObservationModerate(ApiModel):
    moderation_state: Literal["accepted", "rejected"]
    decision_reason: Annotated[str, Field(min_length=2, max_length=500)]


class ApiClientCreate(ApiModel):
    name: Annotated[str, Field(min_length=2, max_length=120)]
    rate_limit_per_minute: Annotated[int | None, Field(ge=1, le=100_000)] = None


class ApiClientView(ApiModel):
    id: uuid.UUID
    name: str
    active: bool
    rate_limit_per_minute: int | None
    created_at: datetime


ApiScope = Literal["routes:read", "observations:write", "webhooks:manage", "admin"]


class ApiKeyCreate(ApiModel):
    name: Annotated[str, Field(min_length=2, max_length=120)]
    scopes: Annotated[set[ApiScope], Field(min_length=1, max_length=4)]
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiry(self) -> ApiKeyCreate:
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None
        ):
            raise ValueError("expires_at must include a UTC offset")
        return self


class ApiKeyCreated(ApiModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    plaintext_key: str


class ApiKeyView(ApiModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


WebhookEventType = Literal["published", "superseded", "stale", "withdrawn"]


class WebhookSubscriptionCreate(ApiModel):
    url: HttpUrl
    event_types: Annotated[set[WebhookEventType], Field(min_length=1, max_length=4)]


class WebhookSubscriptionView(ApiModel):
    id: uuid.UUID
    url: HttpUrl
    event_types: list[str]
    active: bool
    created_at: datetime


class WebhookSubscriptionCreated(WebhookSubscriptionView):
    signing_secret: str


class WebhookSecretRotated(ApiModel):
    id: uuid.UUID
    signing_secret: str


class WebhookDeliveryView(ApiModel):
    id: uuid.UUID
    event_id: uuid.UUID
    state: str
    attempt_count: int
    next_attempt_at: datetime
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime


class WebhookDeliveryPage(ApiModel):
    data: list[WebhookDeliveryView]
    next_cursor: str | None


class ChallengeScoring(ApiModel):
    par_effort: int
    trap_penalty: int = 3


class DailyChallenge(ApiModel):
    id: uuid.UUID
    date: date
    title: str
    graph: RouteGraph
    scoring: ChallengeScoring
    expires_at: datetime
