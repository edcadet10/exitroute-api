"""Operator CLI for migrations, clients, and fictional demo data."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer
from alembic.config import Config
from sqlalchemy import select

from alembic import command
from exitroute.config import get_settings
from exitroute.database import create_database_engine, create_session_factory
from exitroute.domain.graph import RouteGraph
from exitroute.models import ApiClient, Service
from exitroute.schemas import (
    ApiKeyCreate,
    RevisionCreate,
    RouteCreate,
    ServiceCreate,
    Variant,
    VerificationCreate,
)
from exitroute.services.auth import Principal, audit, issue_api_key, utcnow
from exitroute.services.routes import (
    add_verification,
    create_revision,
    create_route,
    create_service,
    publish_revision,
)

app = typer.Typer(help="Operate a self-hosted ExitRoute installation.", no_args_is_help=True)


def _alembic_config() -> Config:
    configured = os.getenv("EXITROUTE_ALEMBIC_CONFIG")
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path.cwd() / "alembic.ini",
            Path(__file__).resolve().parent / "alembic.ini",
            Path(__file__).resolve().parents[2] / "alembic.ini",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return Config(str(candidate.resolve()))
    raise RuntimeError(
        "alembic.ini was not found; run from the repository root or set EXITROUTE_ALEMBIC_CONFIG"
    )


@app.command("migrate")
def migrate() -> None:
    """Upgrade the configured database to the newest schema."""

    command.upgrade(_alembic_config(), "head")


@app.command("create-client")
def create_client(
    name: Annotated[str, typer.Option(prompt=True)],
    admin: Annotated[bool, typer.Option(help="Include the admin scope.")] = False,
) -> None:
    """Create an API client and print its only copy of the plaintext key."""

    settings = get_settings()
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    scopes = {"routes:read", "observations:write", "webhooks:manage"}
    if admin:
        scopes.add("admin")
    principal = Principal(
        actor="operator:cli", client_id=None, key_id=None, scopes=frozenset({"admin"})
    )
    with factory() as session:
        client = ApiClient(name=name.strip())
        session.add(client)
        session.flush()
        key, plaintext = issue_api_key(
            session,
            settings,
            client,
            ApiKeyCreate(name="initial", scopes=scopes),
        )
        audit(session, principal, "api_client.created", "api_client", str(client.id))
        audit(session, principal, "api_key.created", "api_key", str(key.id))
        session.commit()
        typer.echo(f"client_id={client.id}")
        typer.echo(f"api_key={plaintext}")
        typer.echo("Store this key now; it cannot be retrieved later.")
    engine.dispose()


def _demo_graph() -> RouteGraph:
    return RouteGraph.model_validate(
        {
            "entry_node_id": "account",
            "nodes": [
                {
                    "id": "account",
                    "kind": "screen",
                    "state": None,
                    "choices": [
                        {
                            "id": "manage",
                            "label": "Manage membership",
                            "target_node_id": "offer",
                            "effect": "advance",
                            "effort": 1,
                            "prominence": "secondary",
                        }
                    ],
                },
                {
                    "id": "offer",
                    "kind": "screen",
                    "state": None,
                    "choices": [
                        {
                            "id": "keep-plan",
                            "label": "Keep membership",
                            "target_node_id": "retained",
                            "effect": "retain",
                            "effort": 1,
                            "prominence": "primary",
                        },
                        {
                            "id": "continue-exit",
                            "label": "Continue cancellation",
                            "target_node_id": "confirm",
                            "effect": "advance",
                            "effort": 2,
                            "prominence": "subdued",
                        },
                    ],
                },
                {
                    "id": "confirm",
                    "kind": "screen",
                    "state": None,
                    "choices": [
                        {
                            "id": "confirm-exit",
                            "label": "Confirm cancellation",
                            "target_node_id": "cancelled",
                            "effect": "advance",
                            "effort": 1,
                            "prominence": "ambiguous",
                        }
                    ],
                },
                {"id": "retained", "kind": "terminal", "state": "retained", "choices": []},
                {"id": "cancelled", "kind": "terminal", "state": "cancelled", "choices": []},
            ],
        }
    )


@app.command("seed-demo")
def seed_demo() -> None:
    """Idempotently seed one fictional route and a full-scope demo key."""

    settings = get_settings()
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    principal = Principal(
        actor="operator:demo-seed", client_id=None, key_id=None, scopes=frozenset({"admin"})
    )
    with factory() as session:
        existing = session.scalar(select(Service).where(Service.slug == "demo-stream"))
        if existing is not None:
            typer.echo("Demo data already exists; no changes made.")
            engine.dispose()
            return
        service = create_service(
            session,
            ServiceCreate(slug="demo-stream", name="Demo Stream", domains=["example.com"]),
            principal,
            None,
        )
        route = create_route(
            session,
            RouteCreate(service_slug=service.slug, variant=Variant()),
            principal,
            None,
        )
        revision = create_revision(
            session,
            RevisionCreate(
                route_id=route.id,
                entry_url="https://example.com/account",
                graph=_demo_graph(),
                confidence="high",
                change_summary="Fictional demonstration route.",
            ),
            principal,
            None,
        )
        now = utcnow()
        for verifier, environment in (
            ("demo-verifier-a", "clean desktop browser"),
            ("demo-verifier-b", "clean mobile browser"),
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
        publish_revision(
            session,
            revision.id,
            now + timedelta(days=settings.review_window_days),
            settings,
            principal,
            None,
        )
        client = ApiClient(name="Demo client")
        session.add(client)
        session.flush()
        _key, plaintext = issue_api_key(
            session,
            settings,
            client,
            ApiKeyCreate(
                name="demo",
                scopes={"routes:read", "observations:write", "webhooks:manage", "admin"},
            ),
        )
        session.commit()
        typer.echo(f"service_id={service.id}")
        typer.echo(f"route_id={route.id}")
        typer.echo(f"api_key={plaintext}")
        typer.echo("All seeded names and route data are fictional.")
    engine.dispose()
