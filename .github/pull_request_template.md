## What changed

<!-- Describe the behavior and why it belongs in ExitRoute. -->

## Verification

- [ ] Tests cover the changed behavior and a failure case.
- [ ] `uv run ruff check .`, `uv run mypy src/exitroute`, and `uv run pytest` pass.
- [ ] `openapi.yaml` was regenerated if the HTTP contract changed.
- [ ] No credentials, personal data, authenticated screenshots, or real-user evidence were added.
- [ ] Migration, compatibility, privacy, and rollback effects are documented.
