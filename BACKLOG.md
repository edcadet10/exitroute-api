# Ordered implementation backlog

Each item is intended to become one GitHub issue. Work top to bottom unless a
pilot dependency changes the order.

## P0 — prove the core

### ER-001: Bootstrap the Python service

- Create the `src/exitroute` package and application factory.
- Add pinned runtime/dev dependency groups and documented local commands.
- Add `/healthz` and `/readyz`.
- Acceptance: service and tests run from a clean checkout.

### ER-002: Implement graph domain models

- Model service, variant, node, choice, terminal state, revision, and evidence metadata.
- Reject duplicate node/choice IDs, dangling targets, unreachable cancellation,
  invalid terminals, and unknown effects.
- Acceptance: adversarial unit tests cover every invariant.

### ER-003: Implement route selection and friction metrics

- Use deterministic Dijkstra traversal over non-retention choices.
- Define and version the effort-scoring formula.
- Acceptance: labeled fixtures return exact expected paths and stable scores.

### ER-004: Establish PostgreSQL and migrations

- Add relational envelope tables plus immutable JSONB revision payloads.
- Add unique, foreign-key, publication-state, and revision constraints.
- Acceptance: upgrade from empty, downgrade in development, and `alembic check` pass.

### ER-005: Implement editorial revision workflow

- Draft, verify, publish, supersede, withdraw, and mark stale.
- Record actor, timestamp, evidence summary, and reason for every transition.
- Acceptance: a published payload cannot be updated in place.

### ER-006: Seed and independently verify five routes

- Start with five services before committing to 25.
- Verify twice in clean sessions and record discrepancies.
- Acceptance: at least four of five routes reproduce without outside guidance;
  otherwise revise the schema or editorial process first.

## P1 — useful read API

### ER-007: Current exit-route endpoint

- Implement region/platform selection and explicit no-match behavior.
- Return freshness, confidence, graph, best route, friction, and revision metadata.
- Acceptance: response validates against `openapi.yaml`; stale is distinguishable.

### ER-008: Revision history and change feed

- Implement cursor pagination and stable ordering.
- Acceptance: a superseded revision remains fetchable and appears once in changes.

### ER-009: API keys, quotas, and audit logs

- Store only hashed keys; support revoke and rotate.
- Acceptance: anonymous and over-quota requests return documented problem details.

### ER-010: HTTP caching and conditional requests

- Generate ETags from immutable revision fingerprints.
- Acceptance: unchanged conditional request returns `304` with no body.

### ER-011: Developer documentation and SDK example

- Provide curl and one generated client walkthrough.
- Acceptance: an unfamiliar developer reaches a route in under 10 minutes without help.

## P2 — freshness and distribution

### ER-012: Structured observation submission

- Accept semantic changes only; block credentials and obvious PII patterns.
- Add idempotency key and abuse controls.
- Acceptance: submission creates a moderation item and never changes public data.

### ER-013: Review-due and staleness process

- Schedule review reminders and deterministic status transitions.
- Acceptance: overdue data cannot retain `verified` status indefinitely.

### ER-014: Signed webhooks

- Subscribe, rotate secret, deliver, retry, and inspect delivery records.
- Acceptance: signature/replay tests pass and retries are bounded.

### ER-015: Daily challenge projection

- Project a verified route into a link-free, brand-safe playable graph.
- Acceptance: live URLs and private evidence never appear in the challenge payload;
  the reference client never presents effect annotations as hints.

### ER-016: Reference speedrun

- Build one responsive level, timer, replay, anonymous event metrics, and share card.
- Acceptance: no account required; accessibility and keyboard path tested.

### ER-017: Design-partner pilot

- Recruit three finance/privacy/consumer-tool developers.
- Record onboarding time, missing fields, calls made, and integration outcome.
- Acceptance: apply the decision gates in `docs/validation-plan.md` honestly.

## P3 — production readiness after validation

### ER-018: Deployment and recovery runbook

- Automate deploy, migration, rollback, backup, restore test, and key rotation.
- Acceptance: restore drill meets the documented recovery targets.

### ER-019: Observability and service objectives

- Add request metrics, traces, error alerts, freshness dashboard, and webhook alerts.
- Acceptance: injected API, database, and webhook failures are detected.

### ER-020: Pricing experiment

- Keep public single-route access free; test paid bulk/history/webhook/assurance tiers.
- Acceptance: collect explicit willingness-to-pay evidence before billing buildout.
