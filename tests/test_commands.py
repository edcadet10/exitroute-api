from __future__ import annotations

import uuid

import pytest
from typer.testing import CliRunner

from exitroute import jobs
from exitroute.cli import app as cli_app
from exitroute.config import Settings

runner = CliRunner()


@pytest.mark.integration
def test_operator_cli_is_repeatable(postgres_settings: Settings) -> None:
    migrated = runner.invoke(cli_app, ["migrate"])
    assert migrated.exit_code == 0, migrated.output
    created = runner.invoke(
        cli_app, ["create-client", "--name", f"CLI client {uuid.uuid4()}", "--admin"]
    )
    assert created.exit_code == 0, created.output
    assert "Store this key now" in created.output
    seeded = runner.invoke(cli_app, ["seed-demo"])
    assert seeded.exit_code == 0, seeded.output
    repeated = runner.invoke(cli_app, ["seed-demo"])
    assert repeated.exit_code == 0, repeated.output
    assert "already exists" in repeated.output


class DisposableEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_worker_command_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = DisposableEngine()
    settings = Settings(environment="test")
    factory = object()
    monkeypatch.setattr(jobs, "_runtime", lambda: (settings, engine, factory))
    monkeypatch.setattr(jobs, "mark_due_revisions_stale", lambda _factory: 2)
    monkeypatch.setattr(
        jobs,
        "process_due_deliveries",
        lambda _factory, _settings, *, limit: limit,
    )
    jobs.once(batch_size=3)
    assert engine.disposed

    second_engine = DisposableEngine()
    monkeypatch.setattr(jobs, "_runtime", lambda: (settings, second_engine, factory))

    def stop(_factory: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(jobs, "mark_due_revisions_stale", stop)
    jobs.run(batch_size=1, poll_seconds=0.5)
    assert second_engine.disposed
