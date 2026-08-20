"""Shared fixtures, including an opt-in real PostgreSQL database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import SecretStr

from alembic import command
from exitroute.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def postgres_settings() -> Iterator[Settings]:
    database_url = os.getenv("EXITROUTE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("set EXITROUTE_TEST_DATABASE_URL to run PostgreSQL integration tests")
    previous = os.environ.get("EXITROUTE_DATABASE_URL")
    os.environ["EXITROUTE_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    yield Settings(environment="test", database_url=SecretStr(database_url))
    if previous is None:
        os.environ.pop("EXITROUTE_DATABASE_URL", None)
    else:
        os.environ["EXITROUTE_DATABASE_URL"] = previous
    get_settings.cache_clear()
