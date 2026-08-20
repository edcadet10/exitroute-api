"""Replicated-safe background maintenance and outbox worker commands."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Annotated

import typer
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from exitroute.config import Settings, get_settings
from exitroute.database import create_database_engine, create_session_factory
from exitroute.models import RateWindow, RouteRevision
from exitroute.services.auth import Principal, utcnow
from exitroute.services.routes import mark_revision_stale
from exitroute.services.webhooks import process_due_deliveries

app = typer.Typer(help="Run ExitRoute durable background jobs.", no_args_is_help=True)
logger = logging.getLogger(__name__)


def _runtime() -> tuple[Settings, Engine, sessionmaker[Session]]:
    settings = get_settings()
    engine = create_database_engine(settings)
    return settings, engine, create_session_factory(engine)


def mark_due_revisions_stale(factory: sessionmaker[Session], limit: int = 100) -> int:
    system = Principal(
        actor="system:freshness-worker",
        client_id=None,
        key_id=None,
        scopes=frozenset({"admin"}),
    )
    count = 0
    with factory() as session:
        records = list(
            session.scalars(
                select(RouteRevision)
                .where(
                    RouteRevision.publication_state == "published",
                    RouteRevision.trust_state == "verified",
                    RouteRevision.review_due_at <= utcnow(),
                )
                .order_by(RouteRevision.review_due_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for revision in records:
            mark_revision_stale(session, revision.id, system, None)
            count += 1
        session.execute(
            delete(RateWindow).where(RateWindow.window_start < utcnow() - timedelta(minutes=10))
        )
        session.commit()
    return count


@app.command("once")
def once(
    batch_size: Annotated[int, typer.Option(min=1, max=500)] = 50,
) -> None:
    """Run one freshness and webhook delivery pass."""

    settings, engine, factory = _runtime()
    stale = mark_due_revisions_stale(factory)
    deliveries = process_due_deliveries(factory, settings, limit=batch_size)
    typer.echo(f"stale={stale} deliveries={deliveries}")
    engine.dispose()


@app.command("run")
def run(
    batch_size: Annotated[int, typer.Option(min=1, max=500)] = 50,
    poll_seconds: Annotated[float, typer.Option(min=0.5, max=60.0)] = 2.0,
) -> None:
    """Continuously deliver outbox events and enforce freshness."""

    logging.basicConfig(level=logging.INFO)
    settings, engine, factory = _runtime()
    typer.echo("ExitRoute worker started")
    try:
        while True:
            try:
                mark_due_revisions_stale(factory)
                processed = process_due_deliveries(factory, settings, limit=batch_size)
                if processed == 0:
                    time.sleep(poll_seconds)
            except Exception:
                logger.exception("worker pass failed")
                time.sleep(min(poll_seconds * 2, 30))
    except KeyboardInterrupt:
        typer.echo("ExitRoute worker stopped")
    finally:
        engine.dispose()
