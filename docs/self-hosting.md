# Self-hosting

## Development deployment

`docker compose up --build --detach` starts PostgreSQL, runs migrations once,
then starts the API and worker. The API binds to `127.0.0.1:8000`; PostgreSQL is
not published to the host. `docker compose exec api exitroute seed-demo` adds
one fictional route and prints a one-time key.

The Compose defaults are intentionally convenient and intentionally unsafe for
public exposure. Development secrets are rejected when
`EXITROUTE_ENVIRONMENT=production`.

## Production checklist

1. Use PostgreSQL 16 or newer with encrypted storage, automated backups, point-in-time
   recovery, TLS, and a distinct least-privilege application role.
2. Generate independent random values of at least 32 characters for the API-key
   pepper, cursor secret, and webhook master secret. Keep them in your platform's
   secret manager, not a committed `.env` file.
3. Set an HTTPS `EXITROUTE_PUBLIC_BASE_URL`.
4. Set `EXITROUTE_BOOTSTRAP_ADMIN_ENABLED=false`. Production mode refuses to start
   while HTTP bootstrap authentication is enabled.
5. Put the API behind a TLS ingress with body/header/time limits. Do not expose
   PostgreSQL. Keep `/readyz` and operational telemetry on trusted monitoring paths.
6. Run at least two API replicas and enough worker replicas for measured delivery
   lag. Worker leasing is replica-safe.
7. Send process logs and database/audit alerts to durable central storage. Never
   enable request-body or authorization-header logging at a proxy.
8. Run a restore drill before launch and after material database changes.

### First production administrator

The CLI creates credentials directly in the database and therefore does not
need HTTP bootstrap authentication. With production settings already injected:

```bash
docker compose build api
docker compose up --detach database
docker compose run --rm migrate
docker compose run --rm --no-deps api exitroute create-client --name operator --admin
docker compose up --detach api worker
```

Store the printed key immediately. It cannot be retrieved later. Use that admin
key for future client/key lifecycle calls and rotate it on a regular schedule.

## Native process deployment

The container is the supported reproducible artifact. A native installation is
also possible:

```bash
uv sync --frozen --no-dev
uv run exitroute migrate
uv run uvicorn exitroute.app:app --host 127.0.0.1 --port 8000 --no-access-log --no-server-header
uv run exitroute-worker run
```

Run API and worker under separate non-root service accounts. Apply resource,
restart, and file-system restrictions in the process supervisor.

## Configuration

All variables use the `EXITROUTE_` prefix.

| Variable | Meaning | Development default |
|---|---|---|
| `ENVIRONMENT` | `development`, `test`, or guarded `production` | `development` |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL using psycopg | local PostgreSQL |
| `PUBLIC_BASE_URL` | External origin; HTTPS required in production | `http://localhost:8000` |
| `BOOTSTRAP_ADMIN_ENABLED` | Permit the bootstrap HTTP bearer token | `true` |
| `BOOTSTRAP_ADMIN_TOKEN` | Development bootstrap bearer value | known dev value |
| `API_KEY_PEPPER` | HMAC key for API credential digests | known dev value |
| `CURSOR_SECRET` | HMAC key for opaque cursors | known dev value |
| `WEBHOOK_MASTER_SECRET` | Root key for per-subscription signing secrets | known dev value |
| `RATE_LIMIT_PER_MINUTE` | Default per-client quota | `120` |
| `REVIEW_WINDOW_DAYS` | Maximum future verification window | `30` |
| `CORS_ORIGINS` | JSON array of exact allowed browser origins | `[]` |

Do not rotate the API-key pepper without a key migration: existing API keys
will stop authenticating. Cursor-secret rotation invalidates existing cursors,
which is safe. Webhook-master rotation changes derived signing secrets; coordinate
it with every subscriber or rotate subscriptions individually through the API.

## Upgrades and rollback

1. Read [CHANGELOG.md](../CHANGELOG.md) and inspect the migration SQL.
2. Take and verify a restorable backup.
3. Run `exitroute migrate` as a one-off job.
4. Deploy workers and APIs using a rolling strategy; verify `/readyz` and smoke tests.
5. Monitor error rate, latency, database locks, and webhook delivery lag.

Application rollback is safe only while its schema compatibility is documented.
Database downgrades can discard data and are not the primary rollback mechanism;
prefer forward fixes or restore into a new database after an explicitly rehearsed
decision.
