from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from exitroute.app import create_app
from exitroute.config import Settings
from exitroute.domain.graph import RouteGraph, analyze_graph, content_fingerprint
from exitroute.jobs import mark_due_revisions_stale
from exitroute.models import (
    ApiClient,
    ChangeEvent,
    Route,
    RouteRevision,
    Service,
    WebhookDelivery,
    WebhookSubscription,
)
from exitroute.schemas import RevisionCreate, RouteCreate, ServiceCreate, VerificationCreate
from exitroute.services.auth import Principal
from exitroute.services.routes import (
    add_verification,
    create_revision,
    create_route,
    create_service,
    publish_revision,
    withdraw_revision,
)
from exitroute.services.webhooks import process_due_deliveries
from tests.factories import graph_document

pytestmark = pytest.mark.integration
BOOTSTRAP = {"Authorization": "Bearer dev-bootstrap-token-change-me"}


class RecordingSender:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def send(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(204, request=request)


class StatusSender:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def send(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self.status_code, request=request)


def test_full_editorial_public_and_outbox_flow(
    postgres_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(postgres_settings)
    slug = f"test-stream-{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(
        "exitroute.api.webhooks.validate_webhook_url",
        lambda _url: ("hooks.example.com", ("8.8.8.8",)),
    )
    monkeypatch.setattr(
        "exitroute.services.webhooks.validate_webhook_url",
        lambda _url: ("hooks.example.com", ("8.8.8.8",)),
    )
    factory = app.state.session_factory
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200

        created_client = client.post(
            "/admin/v1/api-clients",
            headers=BOOTSTRAP,
            json={"name": f"Integration {slug}"},
        )
        assert created_client.status_code == 201, created_client.text
        client_id = created_client.json()["id"]
        created_key = client.post(
            f"/admin/v1/api-clients/{client_id}/keys",
            headers=BOOTSTRAP,
            json={
                "name": "integration",
                "scopes": ["routes:read", "observations:write", "webhooks:manage"],
            },
        )
        assert created_key.status_code == 201, created_key.text
        key_id = created_key.json()["id"]
        api_headers = {"X-API-Key": created_key.json()["plaintext_key"]}

        webhook = client.post(
            "/v1/webhook-subscriptions",
            headers=api_headers,
            json={"url": "https://hooks.example.com/events", "event_types": ["published"]},
        )
        assert webhook.status_code == 201, webhook.text
        assert webhook.json()["signing_secret"].startswith("whsec_")
        webhook_id = webhook.json()["id"]

        service = client.post(
            "/admin/v1/services",
            headers=BOOTSTRAP,
            json={"slug": slug, "name": "Integration Stream", "domains": ["example.com"]},
        )
        assert service.status_code == 201, service.text
        second_service = client.post(
            "/admin/v1/services",
            headers=BOOTSTRAP,
            json={"slug": f"{slug}-other", "name": "Another Integration Stream"},
        )
        assert second_service.status_code == 201
        route = client.post(
            "/admin/v1/routes",
            headers=BOOTSTRAP,
            json={
                "service_slug": slug,
                "outcome": "cancel_subscription",
                "variant": {"region": "US", "platform": "web"},
            },
        )
        assert route.status_code == 201, route.text
        revision = client.post(
            "/admin/v1/revisions",
            headers=BOOTSTRAP,
            json={
                "route_id": route.json()["id"],
                "entry_url": "https://example.com/account",
                "graph": graph_document(),
                "confidence": "high",
                "change_summary": "Integration fixture published.",
            },
        )
        assert revision.status_code == 201, revision.text
        revision_id = revision.json()["id"]
        assert revision.json()["fingerprint"] != "a" * 64

        first_verification = {
            "verifier": "integration-verifier-a",
            "environment": "clean desktop browser",
            "result": "passed",
            "occurred_at": (now - timedelta(minutes=2)).isoformat(),
        }
        assert (
            client.post(
                f"/admin/v1/revisions/{revision_id}/verifications",
                headers=BOOTSTRAP,
                json=first_verification,
            ).status_code
            == 201
        )
        too_early = client.post(
            f"/admin/v1/revisions/{revision_id}/publish",
            headers=BOOTSTRAP,
            json={"review_due_at": (now + timedelta(days=10)).isoformat()},
        )
        assert too_early.status_code == 409
        assert too_early.json()["code"] == "verification_insufficient"

        second_verification = {
            **first_verification,
            "verifier": "integration-verifier-b",
            "environment": "clean mobile browser",
            "occurred_at": (now - timedelta(minutes=1)).isoformat(),
        }
        assert (
            client.post(
                f"/admin/v1/revisions/{revision_id}/verifications",
                headers=BOOTSTRAP,
                json=second_verification,
            ).status_code
            == 201
        )
        published = client.post(
            f"/admin/v1/revisions/{revision_id}/publish",
            headers=BOOTSTRAP,
            json={"review_due_at": (now + timedelta(days=10)).isoformat()},
        )
        assert published.status_code == 200, published.text
        assert published.json()["publication_state"] == "published"
        assert published.json()["trust_state"] == "verified"

        current = client.get(f"/v1/services/{slug}/exit-route", headers=api_headers)
        assert current.status_code == 200, current.text
        verified_etag = current.headers["etag"]
        assert current.json()["evidence_summary"]["verification_sessions"] == 2
        conditional = client.get(
            f"/v1/services/{slug}/exit-route",
            headers={**api_headers, "If-None-Match": f'W/{verified_etag}, "other"'},
        )
        assert conditional.status_code == 304
        assert conditional.content == b""

        history = client.get(f"/v1/services/{slug}/exit-route/revisions", headers=api_headers)
        assert history.status_code == 200
        assert history.json()["data"][0]["revision"] == 1
        specific = client.get(f"/v1/services/{slug}/exit-route/revisions/1", headers=api_headers)
        assert specific.status_code == 200
        service_page = client.get("/v1/services?limit=1", headers=api_headers)
        assert service_page.status_code == 200
        assert service_page.json()["next_cursor"]
        next_page = client.get(
            "/v1/services",
            headers=api_headers,
            params={"limit": 1, "cursor": service_page.json()["next_cursor"]},
        )
        assert next_page.status_code == 200
        invalid_cursor = client.get(
            "/v1/services", headers=api_headers, params={"cursor": "broken.cursor"}
        )
        assert invalid_cursor.status_code == 400
        assert client.get("/v1/changes", headers=api_headers).status_code == 200
        first_challenge = client.get("/v1/challenges/daily")
        second_challenge = client.get("/v1/challenges/daily")
        assert first_challenge.status_code == second_challenge.status_code == 200
        assert first_challenge.json()["id"] == second_challenge.json()["id"]
        too_old = (now.date() - timedelta(days=31)).isoformat()
        assert client.get("/v1/challenges/daily", params={"date": too_old}).status_code == 422

        observation = {
            "service_slug": slug,
            "outcome": "cancel_subscription",
            "variant": {"region": "US", "platform": "web"},
            "occurred_at": now.isoformat(),
            "change_types": ["choice_label_changed"],
            "note": "The confirmation label changed.",
        }
        observation_headers = {**api_headers, "Idempotency-Key": "0000000000000001"}
        first = client.post("/v1/observations", headers=observation_headers, json=observation)
        duplicate = client.post("/v1/observations", headers=observation_headers, json=observation)
        assert first.status_code == duplicate.status_code == 202
        assert duplicate.json()["duplicate"] is True
        changed = client.post(
            "/v1/observations",
            headers=observation_headers,
            json={**observation, "change_types": ["step_added"]},
        )
        assert changed.status_code == 409
        sensitive = client.post(
            "/v1/observations",
            headers={**api_headers, "Idempotency-Key": "0000000000000002"},
            json={**observation, "note": "email me at person@example.com"},
        )
        assert sensitive.status_code == 422
        moderation_queue = client.get(
            "/admin/v1/observations", headers=BOOTSTRAP, params={"moderation_state": "queued"}
        )
        assert moderation_queue.status_code == 200
        assert any(item["id"] == first.json()["id"] for item in moderation_queue.json()["data"])
        moderated = client.post(
            f"/admin/v1/observations/{first.json()['id']}/moderate",
            headers=BOOTSTRAP,
            json={
                "moderation_state": "accepted",
                "decision_reason": "Plausible report; requires editorial verification.",
            },
        )
        assert moderated.status_code == 200
        assert moderated.json()["moderation_state"] == "accepted"
        repeated_moderation = client.post(
            f"/admin/v1/observations/{first.json()['id']}/moderate",
            headers=BOOTSTRAP,
            json={"moderation_state": "rejected", "decision_reason": "Duplicate."},
        )
        assert repeated_moderation.status_code == 409

        stale = client.post(f"/admin/v1/revisions/{revision_id}/mark-stale", headers=BOOTSTRAP)
        assert stale.status_code == 200
        stale_route = client.get(f"/v1/services/{slug}/exit-route", headers=api_headers)
        assert stale_route.status_code == 200
        assert stale_route.json()["status"] == "stale"
        assert stale_route.headers["etag"] != verified_etag

        changes = client.get("/v1/changes?limit=1", headers=api_headers)
        assert changes.status_code == 200
        assert changes.json()["next_cursor"]

        subscriptions = client.get("/v1/webhook-subscriptions", headers=api_headers)
        assert subscriptions.status_code == 200
        assert any(item["id"] == webhook_id for item in subscriptions.json())
        assert (
            client.get(f"/v1/webhook-subscriptions/{webhook_id}", headers=api_headers).status_code
            == 200
        )
        rotated_secret = client.post(
            f"/v1/webhook-subscriptions/{webhook_id}/rotate-secret", headers=api_headers
        )
        assert rotated_secret.status_code == 200
        assert rotated_secret.json()["signing_secret"] != webhook.json()["signing_secret"]
        deliveries = client.get(
            f"/v1/webhook-subscriptions/{webhook_id}/deliveries", headers=api_headers
        )
        assert deliveries.status_code == 200
        assert deliveries.json()["data"]

        sender = RecordingSender()
        assert process_due_deliveries(factory, postgres_settings, sender=sender) >= 1
        assert sender.requests
        delivered_request = sender.requests[0]
        assert delivered_request.url.host == "8.8.8.8"
        assert delivered_request.headers["host"] == "hooks.example.com"
        assert delivered_request.headers["connection"] == "close"
        assert delivered_request.extensions["sni_hostname"] == "hooks.example.com"
        assert delivered_request.headers["x-exitroute-signature"].startswith("v1=")
        assert (
            client.delete(
                f"/v1/webhook-subscriptions/{webhook_id}", headers=api_headers
            ).status_code
            == 204
        )

        listed_keys = client.get(f"/admin/v1/api-clients/{client_id}/keys", headers=BOOTSTRAP)
        assert listed_keys.status_code == 200
        assert listed_keys.json()[0]["id"] == key_id
        rotated_key = client.post(f"/admin/v1/api-keys/{key_id}/rotate", headers=BOOTSTRAP)
        assert rotated_key.status_code == 201
        replacement_id = rotated_key.json()["id"]
        replacement_headers = {"X-API-Key": rotated_key.json()["plaintext_key"]}

        rejected = client.get(f"/v1/services/{slug}/exit-route", headers=api_headers)
        assert rejected.status_code == 401
        assert rejected.json()["code"] == "inactive_api_key"
        assert (
            client.get(f"/v1/services/{slug}/exit-route", headers=replacement_headers).status_code
            == 200
        )
        revoked = client.delete(f"/admin/v1/api-keys/{replacement_id}", headers=BOOTSTRAP)
        assert revoked.status_code == 204
        rejected = client.get(f"/v1/services/{slug}/exit-route", headers=replacement_headers)
        assert rejected.status_code == 401
        assert rejected.json()["code"] == "inactive_api_key"

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(WebhookDelivery)) >= 1
        with pytest.raises(DBAPIError):
            session.execute(
                update(RouteRevision)
                .where(RouteRevision.id == uuid.UUID(revision_id))
                .values(entry_url="https://example.com/changed")
            )
        session.rollback()


def test_database_rate_limit_is_shared(postgres_settings: Settings) -> None:
    app = create_app(postgres_settings)
    with TestClient(app) as client:
        created_client = client.post(
            "/admin/v1/api-clients",
            headers=BOOTSTRAP,
            json={"name": f"Rate test {uuid.uuid4()}", "rate_limit_per_minute": 1},
        )
        key = client.post(
            f"/admin/v1/api-clients/{created_client.json()['id']}/keys",
            headers=BOOTSTRAP,
            json={"name": "rate", "scopes": ["routes:read"]},
        ).json()["plaintext_key"]
        headers = {"X-API-Key": key}
        assert client.get("/v1/services", headers=headers).status_code == 200
        limited = client.get("/v1/services", headers=headers)
        assert limited.status_code == 429
        assert limited.json()["code"] == "rate_limit_exceeded"
        assert limited.headers["retry-after"] == "60"
        assert (
            client.delete(
                f"/admin/v1/api-clients/{created_client.json()['id']}", headers=BOOTSTRAP
            ).status_code
            == 204
        )
        assert client.get("/v1/services", headers=headers).status_code == 401


def _create_delivery_fixture(
    settings: Settings,
) -> tuple[sessionmaker[Session], uuid.UUID, uuid.UUID]:
    app = create_app(settings)
    factory = app.state.session_factory
    graph = RouteGraph.model_validate(graph_document())
    computed = analyze_graph(graph)
    with factory() as session:
        service = Service(
            slug=f"delivery-{uuid.uuid4().hex[:10]}", name="Delivery Fixture", domains=[]
        )
        client = ApiClient(name=f"Delivery client {uuid.uuid4()}")
        session.add_all([service, client])
        session.flush()
        route = Route(
            service_id=service.id,
            outcome="cancel_subscription",
            region="US",
            platform="web",
        )
        session.add(route)
        session.flush()
        entry_url = f"https://example.com/{uuid.uuid4()}"
        revision = RouteRevision(
            route_id=route.id,
            revision=1,
            publication_state="draft",
            trust_state="provisional",
            entry_url=entry_url,
            graph=graph.model_dump(mode="json"),
            best_route=computed.best_route,
            friction=computed.friction.model_dump(mode="json"),
            algorithm_version="friction-v1",
            fingerprint=content_fingerprint(entry_url, graph, computed),
            confidence="low",
            change_summary="Delivery fixture.",
        )
        session.add(revision)
        session.flush()
        event = ChangeEvent(
            route_id=route.id,
            revision_id=revision.id,
            event_type="published",
            summary="Delivery fixture.",
            occurred_at=datetime.now(UTC),
        )
        subscription = WebhookSubscription(
            client_id=client.id,
            url="https://hooks.example.com/events",
            event_types=["published"],
            secret_salt=secrets.token_bytes(32),
        )
        session.add_all([event, subscription])
        session.flush()
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_id=event.id,
            payload={"id": str(event.id), "type": "route.published", "data": {}},
            next_attempt_at=datetime.now(UTC),
        )
        session.add(delivery)
        session.commit()
        return factory, delivery.id, subscription.id


def test_webhook_retries_then_dead_letters(
    postgres_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, delivery_id, subscription_id = _create_delivery_fixture(postgres_settings)
    monkeypatch.setattr(
        "exitroute.services.webhooks.validate_webhook_url",
        lambda _url: ("hooks.example.com", ("8.8.8.8",)),
    )
    assert (
        process_due_deliveries(factory, postgres_settings, limit=1, sender=StatusSender(500)) == 1
    )
    with factory() as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        assert delivery is not None
        assert delivery.state == "retrying"
        delivery.next_attempt_at = datetime.now(UTC)
        session.commit()
    assert (
        process_due_deliveries(factory, postgres_settings, limit=1, sender=StatusSender(400)) == 1
    )
    with factory() as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        assert delivery is not None
        assert delivery.state == "dead"
        assert delivery.attempt_count == 2
        subscription = session.get(WebhookSubscription, subscription_id)
        assert subscription is not None
        subscription.active = False
        session.commit()


def test_freshness_job_marks_overdue_revision(
    postgres_settings: Settings,
) -> None:
    app = create_app(postgres_settings)
    factory = app.state.session_factory
    graph = RouteGraph.model_validate(graph_document())
    computed = analyze_graph(graph)
    now = datetime.now(UTC)
    with factory() as session:
        service = Service(
            slug=f"overdue-{uuid.uuid4().hex[:10]}", name="Overdue Fixture", domains=[]
        )
        session.add(service)
        session.flush()
        route = Route(
            service_id=service.id,
            outcome="cancel_subscription",
            region="US",
            platform="web",
        )
        session.add(route)
        session.flush()
        entry_url = f"https://example.com/{uuid.uuid4()}"
        revision = RouteRevision(
            route_id=route.id,
            revision=1,
            publication_state="published",
            trust_state="verified",
            entry_url=entry_url,
            graph=graph.model_dump(mode="json"),
            best_route=computed.best_route,
            friction=computed.friction.model_dump(mode="json"),
            algorithm_version="friction-v1",
            fingerprint=content_fingerprint(entry_url, graph, computed),
            confidence="high",
            change_summary="Overdue fixture.",
            verified_at=now - timedelta(days=2),
            review_due_at=now - timedelta(days=1),
            published_at=now - timedelta(days=2),
        )
        session.add(revision)
        session.flush()
        route.current_revision_id = revision.id
        session.commit()
        revision_id = revision.id

    assert mark_due_revisions_stale(factory) >= 1
    with factory() as session:
        revision = session.get(RouteRevision, revision_id)
        assert revision is not None
        assert revision.trust_state == "stale"


def test_supersede_and_withdraw_preserve_history(postgres_settings: Settings) -> None:
    app = create_app(postgres_settings)
    factory = app.state.session_factory
    principal = Principal(
        actor="test:editor", client_id=None, key_id=None, scopes=frozenset({"admin"})
    )
    now = datetime.now(UTC)
    with factory() as session:
        service = create_service(
            session,
            ServiceCreate(slug=f"history-{uuid.uuid4().hex[:10]}", name="History Fixture"),
            principal,
            None,
        )
        route = create_route(session, RouteCreate(service_slug=service.slug), principal, None)

        def verified_revision(path: str, verifier_suffix: str) -> RouteRevision:
            revision = create_revision(
                session,
                RevisionCreate(
                    route_id=route.id,
                    entry_url=f"https://example.com/{path}",
                    graph=RouteGraph.model_validate(graph_document()),
                    change_summary=f"Revision {verifier_suffix}.",
                ),
                principal,
                None,
            )
            for verifier, environment in (
                (f"editor-a-{verifier_suffix}", "desktop clean session"),
                (f"editor-b-{verifier_suffix}", "mobile clean session"),
            ):
                add_verification(
                    session,
                    revision.id,
                    VerificationCreate(
                        verifier=verifier,
                        environment=environment,
                        result="passed",
                        occurred_at=now,
                    ),
                    principal,
                    None,
                )
            return publish_revision(
                session,
                revision.id,
                now + timedelta(days=10),
                postgres_settings,
                principal,
                None,
            )

        first = verified_revision("first", "one")
        second = verified_revision("second", "two")
        assert first.publication_state == "superseded"
        assert route.current_revision_id == second.id
        withdraw_revision(session, second.id, principal, None)
        assert second.publication_state == "withdrawn"
        assert route.current_revision_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(RouteRevision)
                .where(RouteRevision.route_id == route.id)
            )
            == 2
        )
        session.commit()
