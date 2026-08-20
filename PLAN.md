# Build plan

This plan optimizes for one outcome: prove that developers will integrate a
fresh, trustworthy exit-route API before building expensive collection or
automation infrastructure.

Calendar ranges below are solo-builder planning ranges, not delivery promises.

## Product principles

1. **Current beats comprehensive.** Twenty-five recently verified routes are
   more useful than thousands of stale links.
2. **Structure beats prose.** Every published route is a graph that a client can
   render, traverse, score, and diff.
3. **Evidence beats confidence theater.** Every revision records how, when, and
   by whom it was verified.
4. **Privacy by omission.** Published data contains interface semantics, not
   accounts, credentials, screenshots, or personal information.
5. **The API is the product; play is distribution.** The daily challenge is a
   reference client and reporting loop, not a second platform.

## Phase 0 — Contract and risk spike (2–3 days)

Deliverables:

- Freeze the v1 resource names and response envelope in `openapi.yaml`.
- Implement typed graph models and semantic validation.
- Implement deterministic lowest-effort route selection.
- Create adversarial fixtures: deceptive loop, retained terminal, dangling
  edge, phone handoff, and regional/platform variants.
- Record latency and correctness for the fixture suite.

Exit criteria:

- All OpenAPI references resolve and the example validates against its schema.
- All labeled routes return the expected path.
- Invalid graphs fail before publication.
- No fixture requires a service-specific field.

## Phase 1 — Service foundation (3–5 days)

Deliverables:

- Python 3.12+ package with FastAPI, Pydantic, SQLAlchemy, and Alembic.
- PostgreSQL development environment and first migration.
- Configuration through environment variables; no secrets in source control.
- Health, readiness, request ID, structured logging, and RFC 9457 error responses.
- CI for formatting, linting, typing, unit tests, migration checks, and contract checks.

Exit criteria:

- A fresh checkout starts locally from documented commands.
- CI passes from an empty database.
- API schema is generated and diffed against the committed contract.
- Dependency and secret scans run in CI.

## Phase 2 — Editorial data pipeline (5–8 days)

Deliverables:

- Admin-only service, route, draft revision, verification, publish, supersede,
  and withdraw operations.
- Immutable published revisions with an audit trail.
- Seed script for 25 US/web subscription services.
- Editorial checklist and evidence policy.
- Staleness job that marks overdue revisions without deleting history.

Exit criteria:

- Every seeded service has a current revision or an explicit unavailable state.
- Two independent verification sessions reproduce each published best route.
- Publishing a revision cannot mutate or erase an earlier revision.
- PII fixtures are rejected by submission validation and moderation checks.

## Phase 3 — Public read API (4–6 days)

Deliverables:

- Current route, revision history, change feed, and service discovery endpoints.
- API-key authentication, per-key quotas, pagination, ETags, and cache headers.
- Generated SDK example for one client language.
- Public docs with copy-paste requests and error examples.

Exit criteria:

- Contract, integration, authorization, and database tests pass.
- Warm-route reads meet the provisional p95 target of 300 ms in a small load test.
- Conditional GET returns `304` for unchanged revisions.
- Withdrawn or stale data is never presented as currently verified.

## Phase 4 — Observation and freshness loop (5–8 days)

Deliverables:

- PII-free observation submission endpoint with deduplication and abuse limits.
- Moderation queue inside the monolith.
- Change feed cursor and signed webhook delivery with retry records.
- Operational dashboard for due reviews, failed webhooks, and report volume.

Exit criteria:

- Observations cannot directly alter published routes.
- Duplicate and replayed submissions are idempotent.
- Webhook signatures and retry behavior pass integration tests.
- A simulated route change reaches subscribed clients and preserves history.

## Phase 5 — Reference client and pilot (7–10 days)

Deliverables:

- Daily challenge endpoint that strips live links and evidence from the public
  route while preserving the decision mechanics.
- Minimal web speedrun with timer, outcome, and share card.
- Sandbox keys and onboarding for three design partners.
- Pilot instrumentation for integration, replay, sharing, and route usefulness.

Exit criteria:

- At least two design partners complete a sandbox integration, or one signs a
  paid/committed pilot.
- In a 30-person challenge test, at least 50% finish a level, 25% voluntarily
  play another, and 10% share or challenge someone.
- At least 80% of five blinded route-following sessions reach the intended
  cancellation confirmation without external instructions.

If these gates fail, analyze the failures before adding services or automation.

## Phase 6 — Production decision

Proceed only if the Phase 5 gates hold. Then:

- Choose hosting from measured traffic, operational burden, and cost.
- Add billing only after a partner has a billable use case.
- Expand region/platform coverage based on requests, not catalog vanity.
- Add a worker queue only when scheduled verification or webhook volume causes
  measurable request-path contention.
- Evaluate evidence uploads and assisted browsing only after a privacy/legal
  review and a separate threat model.

## Definition of MVP done

The MVP is done only when all of the following are evidenced in the repository
or deployed environment:

- 25 current US/web subscription cancellation graphs
- Versioned, immutable revisions and auditable publication events
- Current-route, history, change-feed, observation, and daily-challenge endpoints
- API-key quotas and documented error behavior
- Automatic graph, schema, migration, security, and integration tests
- Freshness status and review-due behavior
- No credential collection or cancellation automation
- Three pilot invitations and measured results against the published gates
- Runbook for deploy, rollback, database restore, key rotation, and data withdrawal

## Explicitly deferred

- Account deletion, refunds, returns, insurance, and government processes
- Non-US and native mobile flows
- Authenticated scraping or browser automation
- Machine-generated routes published without human verification
- Consumer account linking
- Leaderboards, prizes, social accounts, and native apps
- Microservices, Redis, Kafka, Kubernetes, and a graph database
