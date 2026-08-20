# Contributing

Contributions are welcome under the MIT license. Keep the backend reusable:
features must not assume one cloud, one operator, a private dataset, or access to
consumer accounts.

## Setup

```bash
uv sync --frozen --extra dev
docker compose -f compose.yaml -f compose.test.yaml up --detach database
export EXITROUTE_TEST_DATABASE_URL=postgresql+psycopg://exitroute:exitroute@localhost:55432/exitroute
uv run pytest
```

Before opening a pull request, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/exitroute
uv run python scripts/export_openapi.py --check
uv run pytest --cov
```

If the contract changes, run `uv run python scripts/export_openapi.py` and commit
both generated artifacts. If persistence changes, add an Alembic revision and
verify upgrade, downgrade in an isolated database, upgrade again, and `alembic check`.

## Design expectations

- Put graph/security rules in the pure domain layer and transactions in services.
- Make server-derived values impossible for clients to override.
- Preserve published revision, audit, and change history.
- Add a failure-oriented test for every meaningful invariant or security boundary.
- Keep errors machine-readable and OpenAPI behavior accurate.
- Avoid new infrastructure until a measured trigger is documented.
- Never commit credentials, personal data, authenticated evidence, or real-brand
  route material without rights and policy review.

Small, focused pull requests are easiest to review. Explain compatibility,
migration, privacy, operational, and rollback effects in the pull request template.

## Reporting route changes

This repository intentionally ships only fictional data. A future data repository
should use its own license and verification workflow. Do not put unreviewed real
service routes or user evidence into source-code pull requests.
