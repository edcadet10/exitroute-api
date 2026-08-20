# ExitRoute API

ExitRoute is a self-hosted API for publishing factual, versioned routes through
subscription-cancellation flows. It models each flow as a decision graph,
computes the lowest-friction safe path, keeps immutable revision history, and
offers a link-free daily puzzle generated from the same data.

The repository is an alpha that runs end to end. It contains no real-brand
catalog and no personal data; the included seed is deliberately fictional.

## Run it

Requirements: Docker Engine with Compose v2.

```bash
git clone https://github.com/edcadet10/exitroute-api.git
cd exitroute-api
docker compose up --build --detach
docker compose exec api exitroute seed-demo
```

The last command prints a demo API key once. Use it in place of `$API_KEY`:

```bash
curl --header "X-API-Key: $API_KEY" \
  "http://localhost:8000/v1/services/demo-stream/exit-route?region=US&platform=web"
```

- Interactive API docs: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/healthz>
- Readiness: <http://localhost:8000/readyz>
- Public daily challenge: <http://localhost:8000/v1/challenges/daily>

The default Compose configuration binds only to `127.0.0.1` and uses known
development secrets. It is not a production configuration. Follow
[the self-hosting guide](docs/self-hosting.md) before exposing it to a network.

## What is implemented

- Strict graph semantics, deterministic route selection, and versioned friction scoring
- Separate publication (`draft`, `published`, `superseded`, `withdrawn`) and trust
  (`provisional`, `verified`, `stale`) state machines
- Two-independent-session publication gate and database-enforced immutable published content
- Scoped, hashed API keys with rotation, revocation, expiration, and PostgreSQL-backed quotas
- Signed opaque pagination cursors and state-aware ETags with conditional GET support
- Structured, PII-filtered, idempotent observations that always enter moderation
- Transactional webhook outbox, replica-safe leasing, TLS/DNS SSRF defenses, retry, and dead letters
- Scheduled freshness enforcement and public, URL-free challenge projections
- Alembic migrations, locked dependencies, non-root/read-only containers, and pinned CI actions
- Generated OpenAPI 3.1 plus an OpenAPI 3.0 artifact for Cloudflare API Shield import

## API shape

| Surface | Purpose | Authentication |
|---|---|---|
| `/v1/services`, exit routes, revisions, `/v1/changes` | Read the catalog and history | `routes:read` API key |
| `/v1/observations` | Submit a bounded change report | `observations:write` API key |
| `/v1/webhook-subscriptions` | Manage signed change delivery | `webhooks:manage` API key |
| `/v1/challenges/daily` | Play a link-free route puzzle | Public |
| `/admin/v1/*` | Editorial workflow and credential lifecycle | Admin key or development bootstrap token |

See [openapi.yaml](openapi.yaml) for the canonical contract and
[openapi.cloudflare.yaml](openapi.cloudflare.yaml) for the deliberately reduced
OpenAPI 3.0 validation artifact.

## Trust model

ExitRoute is informational. It never logs in to a service, clicks on a user's
behalf, receives account credentials, or claims a cancellation succeeded. Raw
community observations cannot modify public data. Publishing requires a typed
graph, two distinct successful verification sessions, a future review date,
and an editor action. When that date passes, the worker and read path both stop
describing the route as verified.

Webhook destinations must be HTTPS on port 443 and resolve entirely to public
addresses. Delivery pins the vetted address while retaining TLS hostname
verification, follows no redirects, signs the exact body, and never logs the
signing secret.

## Develop

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --frozen --extra dev
docker compose -f compose.yaml -f compose.test.yaml up --detach database
export EXITROUTE_TEST_DATABASE_URL=postgresql+psycopg://exitroute:exitroute@localhost:55432/exitroute
uv run pytest
uv run ruff check .
uv run mypy src tests
```

The suite uses a real PostgreSQL database for persistence, concurrency, trigger,
and outbox behavior. Branch coverage must remain at or above 85%.

## Project map

- [docs/architecture.md](docs/architecture.md) — boundaries, request paths, and scaling triggers
- [docs/data-model.md](docs/data-model.md) — relational model and invariants
- [docs/verification-policy.md](docs/verification-policy.md) — evidence and moderation policy
- [docs/self-hosting.md](docs/self-hosting.md) — production configuration and upgrades
- [docs/operations.md](docs/operations.md) — reliability targets, backup, restore, and incident runbooks
- [docs/webhooks.md](docs/webhooks.md) — signature verification, replay defense, and retries
- [CONTRIBUTING.md](CONTRIBUTING.md) — development and review expectations
- [SECURITY.md](SECURITY.md) — private vulnerability reporting

The earlier product validation work remains in [PLAN.md](PLAN.md),
[BACKLOG.md](BACKLOG.md), and [docs/validation-plan.md](docs/validation-plan.md).
Those documents distinguish engineering readiness from evidence of market demand.

## License

[MIT](LICENSE). You may use, modify, and distribute the software. Route data you
add remains your responsibility: confirm that you have the right to publish it,
keep private evidence out of public payloads, and obtain legal advice for your
jurisdiction and use case.
