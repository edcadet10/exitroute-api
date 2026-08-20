<p align="center">
  <img src="assets/banner.svg" alt="ExitRoute — verified, versioned cancellation routes as a self-hosted API" width="100%">
</p>

<p align="center">
  <a href="https://github.com/edcadet10/exitroute-api/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/edcadet10/exitroute-api/ci.yml?branch=main&amp;style=flat-square&amp;label=CI" alt="CI status"></a>
  <a href="https://github.com/edcadet10/exitroute-api/actions/workflows/codeql.yml"><img src="https://img.shields.io/github/actions/workflow/status/edcadet10/exitroute-api/codeql.yml?branch=main&amp;style=flat-square&amp;label=CodeQL" alt="CodeQL status"></a>
  <a href="https://github.com/edcadet10/exitroute-api/releases/latest"><img src="https://img.shields.io/github/v/release/edcadet10/exitroute-api?style=flat-square&amp;color=4ecca3" alt="Latest release"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.12"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-f5b14e?style=flat-square" alt="MIT license"></a>
</p>

<p align="center"><b>Publish factual cancellation flows as API-ready decision graphs—with verification, history, webhooks, and a playable daily challenge.</b></p>

---

> [!IMPORTANT]
> ExitRoute is an alpha data API, not a cancellation bot. It never signs in, clicks for a user, stores account credentials, or claims a cancellation succeeded. The bundled catalog is fictional.

## Quick start

You need Docker Engine with Compose v2.

```bash
git clone https://github.com/edcadet10/exitroute-api.git
cd exitroute-api
docker compose up --build --detach
docker compose exec api exitroute seed-demo
```

The seed command prints an API key once. Copy it, then request the fictional route:

```bash
export API_KEY='paste-the-printed-value'
curl --header "X-API-Key: $API_KEY" \
  "http://localhost:8000/v1/services/demo-stream/exit-route?region=US&platform=web"
```

- API explorer: <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/readyz>
- Public daily challenge: <http://localhost:8000/v1/challenges/daily>

The defaults bind the API to `127.0.0.1` and use known development secrets. Read the [self-hosting guide](docs/self-hosting.md) before exposing it to a network.

## What it provides

| Capability | What it does |
| --- | --- |
| Route graphs | Versioned screens, choices, loops, offers, handoffs, and terminal states |
| Analysis | Deterministic safe paths, friction scores, and graph fingerprints |
| Editorial trust | Two independent verifications, immutable history, and explicit withdrawal |
| Feedback | PII-filtered, idempotent observations that always enter moderation |
| Delivery | Signed webhooks, transactional outbox, SSRF defenses, and bounded retry |
| Daily puzzle | A public, link-free challenge derived from verified routes |

```mermaid
flowchart LR
    O([Observation]) --> M[Moderation]
    M --> D[Draft graph]
    D --> V[Two clean-session<br/>verifications]
    V --> P([Published revision])
    P --> A[Read API]
    P --> W[Signed webhooks]
    P --> C[Daily challenge]

    classDef input fill:#11161f,stroke:#22d3ee,color:#d9f7fb
    classDef work fill:#11161f,stroke:#4ecca3,color:#d8f5e9
    classDef publish fill:#0f2a22,stroke:#f5b14e,color:#fff0d7
    class O input
    class M,D,V,A,W,C work
    class P publish
```

## API at a glance

| Surface | Purpose | Authentication |
| --- | --- | --- |
| `/v1/services`, exit routes, revisions, `/v1/changes` | Catalog and immutable history | `routes:read` API key |
| `/v1/observations` | Submit a bounded change report | `observations:write` API key |
| `/v1/webhook-subscriptions` | Manage signed change delivery | `webhooks:manage` API key |
| `/v1/challenges/daily` | Play the link-free route puzzle | Public |
| `/admin/v1/*` | Editorial and credential lifecycle | Admin API key; bootstrap token in development only |

The canonical contract is [OpenAPI 3.1](openapi.yaml); a reduced [OpenAPI 3.0 artifact](openapi.cloudflare.yaml) supports Cloudflare API Shield.

## Safety and production

- Public revisions contain interface semantics—not credentials, cookies, screenshots, or personal evidence.
- Publication, trust, withdrawal, and freshness are database-enforced states.
- Webhooks allow only vetted public HTTPS targets and preserve TLS hostname verification.
- Self-hosters control their infrastructure and data; no real-brand catalog is included.

Compose is a local starting point, not a public ingress. Before production, follow the [self-hosting checklist](docs/self-hosting.md) and [operations runbooks](docs/operations.md).

## Develop

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --frozen --extra dev
docker compose -f compose.yaml -f compose.test.yaml up --detach database
export EXITROUTE_TEST_DATABASE_URL=postgresql+psycopg://exitroute:exitroute@localhost:55432/exitroute

uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run python scripts/export_openapi.py --check
```

Tests use real PostgreSQL and enforce at least 85% branch coverage.

## Documentation

| Guide | Use it for |
| --- | --- |
| [Architecture](docs/architecture.md) | Boundaries and scaling triggers |
| [Data model](docs/data-model.md) | Tables and invariants |
| [Verification](docs/verification-policy.md) | Evidence and publication policy |
| [Self-hosting](docs/self-hosting.md) | Configuration, upgrades, and rollback |
| [Operations](docs/operations.md) | Backups, alerts, and incidents |
| [Webhooks](docs/webhooks.md) | Signatures, retries, and dead letters |
| [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) | Development and disclosure |

## Status and license

[v0.1.0](https://github.com/edcadet10/exitroute-api/releases/tag/v0.1.0) is a tested alpha with fictional data. Catalog demand and real-route coverage remain unvalidated; see [PLAN.md](PLAN.md).

[MIT](LICENSE). You may use, modify, and distribute the software. You remain responsible for the legality, accuracy, and publication rights of route data you add.
