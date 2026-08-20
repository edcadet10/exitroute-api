# Contributing

Thanks for helping improve ExitRoute. Documentation, tests, bug fixes, and
provider-neutral backend features are all welcome.

## Start here

- For a small fix, open a focused pull request directly.
- For a reproducible bug or feature proposal, use an [issue form](https://github.com/edcadet10/exitroute-api/issues/new/choose).
- For a broad API, data-model, or architecture change, start a [Discussion](https://github.com/edcadet10/exitroute-api/discussions) first.
- Report vulnerabilities through [GitHub's private reporting form](https://github.com/edcadet10/exitroute-api/security/advisories/new), never a public issue.

You do not need an assignment for an unclaimed small issue. Comment before
starting larger work so contributors do not duplicate effort. Draft pull
requests are welcome.

## Local setup

```bash
uv sync --frozen --extra dev
docker compose -f compose.yaml -f compose.test.yaml up --detach database
export EXITROUTE_TEST_DATABASE_URL=postgresql+psycopg://exitroute:exitroute@localhost:55432/exitroute
uv run pytest
```

## Project guardrails

- Keep the backend reusable across clouds, operators, and datasets.
- Put graph and security rules in the pure domain layer; keep transactions in services.
- Make server-derived values impossible for clients to override.
- Preserve published revision, audit, and change history.
- Add a failure-oriented test for every meaningful invariant or security boundary.
- Keep errors machine-readable and OpenAPI behavior accurate.
- Avoid new infrastructure until a measured scaling trigger is documented.
- Never add credentials, personal data, authenticated evidence, or real-brand route material without rights and policy review.

## Before opening a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run python scripts/export_openapi.py --check
uv run python scripts/validate_contract.py
uv run pytest
```

If the contract changes, run `uv run python scripts/export_openapi.py` and commit
both generated artifacts. If persistence changes, add an Alembic revision and
verify upgrade, downgrade in an isolated database, upgrade again, and `alembic check`.

Keep pull requests focused on one concern. Link the relevant issue, explain the
user-visible effect, and document compatibility, migration, privacy,
operational, and rollback implications. Maintainers may ask to split unrelated
changes before review.

## Reporting route changes

This repository intentionally ships only fictional data. A future data repository
should use its own license and verification workflow. Do not put unreviewed real
service routes or user evidence into source-code pull requests.

Participation in this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
