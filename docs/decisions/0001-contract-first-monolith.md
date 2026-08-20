# ADR 0001: Contract-first modular monolith

- Status: proposed
- Date: 2026-08-20

## Context

The riskiest unknowns are whether route data is useful, can stay current, and
can be collected safely. Raw API throughput and organizational scaling are not
current constraints. The service nevertheless needs a stable external contract,
strong graph validation, revision history, and transactional publication.

## Decision

Build a contract-first modular monolith using:

- Python and FastAPI for HTTP and generated OpenAPI
- Pydantic for boundary/domain validation
- SQLAlchemy and Alembic for persistence and migrations
- PostgreSQL for relational identity/audit data and JSONB revision graphs
- A deterministic domain-level Dijkstra implementation for recommended paths
- Platform scheduling plus a same-codebase CLI for freshness jobs

Use OpenAPI 3.1 for the committed contract because it aligns with FastAPI's
JSON-Schema-based modeling and has broad tooling support. The currently latest
OpenAPI publication is newer; adopting its minor version is not needed to test
the MVP and should follow actual tool compatibility.

## Alternatives considered

### Graph database

Rejected for the MVP. Traversal is bounded inside one small immutable revision,
not across a massive interconnected graph. Reconsider only with measured query
requirements PostgreSQL cannot meet.

### Document database

Rejected for the MVP. Graph documents fit, but publication pointers, monotonic
revisions, client quotas, audit records, and webhook deliveries benefit from
relational constraints and transactions.

### Microservices and queue from day one

Rejected for the MVP. There is no demonstrated scale or team boundary. Durable
database rows and a scheduler cover initial webhook and freshness work.

### SQLite through production pilot

Useful for isolated domain tests, but rejected as the production target because
the design depends on concurrent editorial/public use, JSONB operations, and a
production migration path. Using the production database in CI also reduces
dialect-specific surprises.

## Falsification

Kill or revise this decision if the contract/domain spike cannot validate all
required flow variants, if PostgreSQL operations dominate a representative read
latency budget, or if operational measurements show durable asynchronous work
cannot be handled safely in the monolith.

A five-variant temporary graph spike passed. The repository contract validator
and Phase 0 implementation must independently reproduce that result.

## Consequences

- One deployment and transaction boundary keep the pilot understandable.
- The external contract can evolve independently of internal modules.
- JSONB schema correctness must be enforced in application validation and tests.
- Background execution is intentionally modest and may need extraction later.
- Published revision immutability must be protected at both application and
  database permission/constraint layers.

## Sources

- [FastAPI features](https://fastapi.tiangolo.com/features/)
- [PostgreSQL JSONB documentation](https://www.postgresql.org/docs/current/datatype-json.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Alembic documentation](https://alembic.sqlalchemy.org/en/latest/)
