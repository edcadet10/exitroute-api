# Data model

## Storage strategy

Use relational columns for values that identify, filter, constrain, or audit a
route. Use a JSONB document for the bounded node/choice graph belonging to a
specific immutable revision.

This avoids two bad extremes: an opaque document store with weak publication
constraints, and many graph tables that make a revision difficult to copy,
validate, fingerprint, and return atomically.

## Tables

### `services`

| Column | Purpose |
|---|---|
| `id` UUID | Stable internal identity |
| `slug` text unique | Public identifier |
| `name` text | Display name |
| `domains` text[] | Exact domains used for discovery |
| `active` boolean | Catalog state |
| timestamps | Audit metadata |

### `routes`

One logical variant per service/outcome/region/platform.

| Column | Purpose |
|---|---|
| `id` UUID | Stable route identity |
| `service_id` UUID FK | Owning service |
| `outcome` enum | Initially `cancel_subscription` |
| `region` char(2) | ISO 3166-1 alpha-2 code |
| `platform` enum | Initially `web`; model allows later variants |
| `current_revision_id` UUID nullable | Published pointer maintained transactionally |

Unique constraint: `(service_id, outcome, region, platform)`.

### `route_revisions`

| Column | Purpose |
|---|---|
| `id` UUID | Revision identity |
| `route_id` UUID FK | Logical route |
| `revision` integer | Monotonic route-local number |
| `state` enum | `draft`, `verified`, `published`, `stale`, `withdrawn`, `superseded` |
| `entry_url` text | Starting page; only on non-challenge representation |
| `graph` JSONB | Nodes and choices |
| `best_route` JSONB | Ordered choice IDs calculated at publication |
| `friction` JSONB | Versioned metrics calculated at publication |
| `algorithm_version` text | Reproducibility |
| `fingerprint` text unique | Canonical payload digest |
| verification/review timestamps | Freshness state |
| actor/reason fields | Auditability |

Unique constraint: `(route_id, revision)`. Published rows are append-only. A
database trigger or restricted persistence API should reject in-place updates
to immutable payload fields after publication.

### `verification_events`

Records each attempt independently, including result, environment description,
evidence references, discrepancies, verifier identity, and timestamp. Evidence
references are private metadata, never embedded in the public graph.

### `observations`

Structured reports from clients. Store service/variant, observed revision,
semantic change type, bounded explanation, occurrence time, idempotency key,
moderation state, and reporter client ID. An observation can create a draft but
cannot publish.

### `api_clients`, `webhook_subscriptions`, and `webhook_deliveries`

Hold hashed API credentials, plans/quotas, signing-secret metadata, event
subscriptions, delivery attempts, response codes, and retry state. Never log
plaintext credentials or signing secrets.

### `audit_events`

Append-only record of security- and publication-relevant actions. Store actor,
action, object identity, timestamp, request ID, and minimal structured context.

## Graph document

Every graph contains:

- `entry_node_id`
- An array of nodes with unique IDs
- A node kind: `screen`, `os_settings`, `handoff`, or `terminal`
- Optional terminal state: `cancelled`, `retained`, or `unavailable`
- Choices with unique IDs, user-visible labels, target node IDs, effect, and effort

Choice effects are `advance`, `loop`, `retain`, or `handoff`. A retention choice
can be represented and rendered, but cannot appear in the recommended exit path.

## Publication invariants

A revision cannot be published unless all invariants hold:

1. Entry node exists.
2. Node IDs and choice IDs are unique.
3. Every target resolves to a node in the same revision.
4. At least one `cancelled` terminal is reachable from the entry.
5. Terminal nodes have no choices.
6. The best route ends at `cancelled` and includes no `retain` choice.
7. Recomputing the path and friction with `algorithm_version` matches stored values.
8. Region, platform, outcome, entry URL, and dates pass strict validation.
9. Verification requirements and review date are satisfied.
10. Canonical serialization matches the stored fingerprint.

## Revision rules

- Drafts may change.
- Publishing creates or locks an immutable payload and atomically updates the
  route's current pointer.
- Superseding never deletes history.
- Staleness changes the trust state, not historical contents.
- Withdrawal removes a revision from normal discovery but retains the audit record.
- Correcting a published typo produces a new revision.
