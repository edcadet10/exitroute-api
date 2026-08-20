# Operations and reliability

These are operator targets, not measured claims about an undeployed repository.
Each deployment should replace them with objectives tied to its users and budget.

## Suggested service objectives

| Signal | Initial objective | Measurement |
|---|---|---|
| Keyed read availability | 99.9% successful non-5xx responses per rolling 30 days | ingress plus application metrics |
| Keyed read latency | p95 below 250 ms, p99 below 750 ms | server duration excluding client network |
| Publication durability | no acknowledged publication without revision, audit, change, and outbox rows | transaction/invariant alerts |
| Webhook lag | 99% of healthy-endpoint deliveries attempted within 60 seconds | `created_at` to first attempt |
| Freshness enforcement | overdue revision loses `verified` within 5 minutes | due timestamp to stale event |

Suggested pilot recovery objectives are RPO ≤ 5 minutes and RTO ≤ 60 minutes,
provided PostgreSQL WAL archiving, cross-failure-domain backups, and rehearsed
automation actually support them. Without those controls, advertise no such
objective.

## Signals to collect

- HTTP count, status, route template, and duration; never raw API keys or query values.
- PostgreSQL connection saturation, query latency, locks, replication lag, storage,
  backup age, and restore-check results.
- Pending/retrying/dead webhook counts, oldest due row, attempts, and response class.
- Number and age of verified, stale, draft, and observation records.
- Authentication failures, rate-limit events, admin actions, and unexpected trigger rejects.
- API/worker restarts, CPU, memory, file descriptors, and outbound connection errors.

The application emits request IDs and stores them on security-relevant audit
events. Configure the ingress to preserve or generate `X-Request-ID`, but never
trust it as identity.

## Backup and restore runbook

1. Use continuous WAL archiving or a managed equivalent plus daily independent snapshots.
2. Encrypt backups with a key separated from database credentials and test access controls.
3. Restore into an isolated database at least quarterly.
4. Run `alembic current`, readiness, a catalog read, revision-history check, and
   counts/checksums for revisions, audit events, changes, and outbox rows.
5. Record achieved RPO/RTO and fix gaps before claiming the target.

Never validate a restore by overwriting the only production database.

## Incident: database unavailable

1. Confirm `/healthz` remains live while `/readyz` returns 503.
2. Stop automated restarts if they amplify connection pressure.
3. Check provider/database events, capacity, locks, and credential rotation.
4. Fail over only through a rehearsed procedure. Confirm transaction consistency.
5. Re-enable workers gradually; watch outbox backlog and connection utilization.

## Incident: webhook backlog

1. Measure oldest due row and split response codes from network failures.
2. Confirm DNS policy and egress changes did not block valid destinations.
3. Scale workers only if PostgreSQL and downstream limits have headroom.
4. Do not reset attempt counts or bulk replay dead deliveries without subscriber approval.
5. Rotate a subscription secret if exposure is suspected; coordinate the cutover.

## Incident: incorrect public route

1. Withdraw the current revision through the admin API; do not edit its JSON in place.
2. Preserve verification and observation records for investigation.
3. Create a corrected draft and repeat independent verification.
4. Notify webhook consumers using the normal change stream.
5. Document how the verification policy or validator should change.

## Secret compromise

- API key: rotate/revoke that key; audit its client activity.
- Cursor secret: rotate immediately; clients will restart pagination.
- Webhook subscription secret: rotate the subscription and notify that subscriber.
- Webhook master secret: treat every derived secret as affected and coordinate a full rotation.
- API-key pepper: create replacement client keys under a planned dual-pepper migration;
  an immediate uncoordinated change invalidates every key.
