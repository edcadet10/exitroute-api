"""Relational persistence models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonDocument = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Service(Base, TimestampMixin):
    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    domains: Mapped[list[str]] = mapped_column(JsonDocument, default=list, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Route(Base, TimestampMixin):
    __tablename__ = "routes"
    __table_args__ = (
        CheckConstraint("region ~ '^[A-Z]{2}$'", name="ck_routes_region"),
        CheckConstraint("outcome = 'cancel_subscription'", name="ck_routes_outcome"),
        ForeignKeyConstraint(
            ["id", "current_revision_id"],
            ["route_revisions.route_id", "route_revisions.id"],
            name="fk_routes_current_revision",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        UniqueConstraint("service_id", "outcome", "region", "platform", name="uq_route_variant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    region: Mapped[str] = mapped_column(String(2), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        nullable=True,
    )

    service: Mapped[Service] = relationship()


class RouteRevision(Base, TimestampMixin):
    __tablename__ = "route_revisions"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_revisions_positive_revision"),
        CheckConstraint("status_version > 0", name="ck_revisions_positive_status_version"),
        CheckConstraint(
            "publication_state IN ('draft', 'published', 'superseded', 'withdrawn')",
            name="ck_revisions_publication_state",
        ),
        CheckConstraint(
            "trust_state IN ('provisional', 'verified', 'stale')",
            name="ck_revisions_trust_state",
        ),
        CheckConstraint("entry_url LIKE 'https://%'", name="ck_revisions_https_entry"),
        CheckConstraint("fingerprint ~ '^[a-f0-9]{64}$'", name="ck_revisions_fingerprint"),
        CheckConstraint(
            "review_due_at IS NULL OR verified_at IS NULL OR review_due_at > verified_at",
            name="ck_revisions_review_after_verification",
        ),
        CheckConstraint(
            "publication_state = 'draft' OR "
            "(verified_at IS NOT NULL AND review_due_at IS NOT NULL "
            "AND published_at IS NOT NULL)",
            name="ck_revisions_published_dates",
        ),
        UniqueConstraint("route_id", "revision", name="uq_route_revision_number"),
        UniqueConstraint("route_id", "id", name="uq_route_revision_identity"),
        UniqueConstraint("route_id", "fingerprint", name="uq_route_revision_fingerprint"),
        Index("ix_revision_publication_trust", "publication_state", "trust_state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    publication_state: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    trust_state: Mapped[str] = mapped_column(String(20), default="provisional", nullable=False)
    status_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    entry_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    graph: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    best_route: Mapped[list[str]] = mapped_column(JsonDocument, nullable=False)
    friction: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[str] = mapped_column(String(12), default="low", nullable=False)
    change_summary: Mapped[str] = mapped_column(String(280), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationEvent(Base):
    __tablename__ = "verification_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("route_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verifier: Mapped[str] = mapped_column(String(120), nullable=False)
    environment: Mapped[str] = mapped_column(String(280), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiClient(Base, TimestampMixin):
    __tablename__ = "api_clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    secret_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JsonDocument, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    client: Mapped[ApiClient] = relationship()


class RateWindow(Base):
    __tablename__ = "rate_windows"
    __table_args__ = (UniqueConstraint("client_id", "window_start", name="uq_rate_window"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "moderation_state IN ('queued', 'accepted', 'rejected')",
            name="ck_observations_moderation_state",
        ),
        CheckConstraint(
            "(moderation_state = 'queued' AND moderated_at IS NULL "
            "AND moderated_by IS NULL AND decision_reason IS NULL) OR "
            "(moderation_state <> 'queued' AND moderated_at IS NOT NULL "
            "AND moderated_by IS NOT NULL AND decision_reason IS NOT NULL)",
            name="ck_observations_moderation_fields",
        ),
        UniqueConstraint("client_id", "idempotency_key", name="uq_observation_idempotency"),
        Index("ix_observations_queue", "moderation_state", "received_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    moderation_state: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderated_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChangeEvent(Base):
    __tablename__ = "change_events"

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4, nullable=False)
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("route_revisions.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(String(280), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebhookSubscription(Base, TimestampMixin):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("api_clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JsonDocument, nullable=False)
    secret_salt: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("subscription_id", "event_id", name="uq_delivery_subscription_event"),
        Index("ix_delivery_due", "state", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_events.id", ondelete="CASCADE"), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscription: Mapped[WebhookSubscription] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4, nullable=False)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[str] = mapped_column(String(80), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JsonDocument, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChallengeAssignment(Base):
    __tablename__ = "challenge_assignments"

    challenge_date: Mapped[date] = mapped_column(Date, primary_key=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("route_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, default=uuid.uuid4, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
