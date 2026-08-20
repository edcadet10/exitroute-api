"""SQLAlchemy engine and transaction helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from exitroute.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create a pre-pinging engine without leaking credentials into logs."""

    url = settings.database_url.get_secret_value()
    options: dict[str, object] = {"pool_pre_ping": True}
    if not url.startswith("sqlite"):
        options.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    return create_engine(url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a transaction and always close its session."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
