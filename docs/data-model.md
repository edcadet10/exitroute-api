# Data model and invariants

Identity, filtering, workflow, and audit fields are relational. Each bounded
route graph is a JSONB value attached to an immutable revision. This keeps
publication atomic while retaining database constraints on the state envelope.

## Main records

- `services`: public slug/name, optional discovery domains, active flag.
- `routes`: unique service/outcome/region/platform identity and current revision pointer.
- `route_revisions`: graph content, derived route/friction/fingerprint, separate
  publication and trust states, and verification/review timestamps.
- `verification_events`: independent result, verifier, environment, time, and
  private evidence reference; evidence is never copied into a public response.
- `api_clients` and `api_keys`: quota owner, keyed credential digest, prefix,
  scopes, expiry, use time, and revocation time.
- `observations`: client-scoped idempotency key, canonical payload hash, bounded
  report, and moderation state.
- `change_events` and `audit_events`: append-only public and security histories.
- `webhook_subscriptions` and `webhook_deliveries`: destination configuration,
  derivation salt, immutable event payload, lease/retry state, and result metadata.
- `rate_windows`: one atomic per-client/per-minute counter shared by all API replicas.
- `challenge_assignments`: stable date-to-revision mapping so catalog changes do
  not change a puzzle after it is first served.

## Graph invariants

Publication uses the pure domain validator and rejects a graph unless:

1. Node and choice IDs are globally unique inside the revision.
2. The entry and every target exist; every node is reachable from the entry.
3. Terminal kind and terminal state agree exactly, terminal nodes have no choices,
   and nonterminal nodes have at least one choice.
4. A `retain` choice ends at a retained terminal; an `advance` choice cannot do so.
5. A `handoff` choice targets a handoff node.
6. A `loop` label describes an actual cycle.
7. A path excluding retain and loop edges reaches a cancelled terminal.
8. Deterministic lowest-effort selection ends at cancellation; lexicographic choice
   IDs break equal-cost ties.
9. Recomputed friction and canonical SHA-256 fingerprint match server-derived values.

Clients cannot provide `best_route`, `friction`, `algorithm_version`, or
`fingerprint` when creating a draft.

## State model

Publication state and trust state answer different questions:

| Publication | Meaning |
|---|---|
| `draft` | Editorial work; never public |
| `published` | Current public candidate for its variant |
| `superseded` | Immutable historical revision replaced by another |
| `withdrawn` | Retained for audit but removed from normal public discovery |

| Trust | Meaning |
|---|---|
| `provisional` | Not eligible for publication |
| `verified` | Passed policy and still within its review window |
| `stale` | Review window elapsed or an editor explicitly removed the verified label |

Changing trust does not rewrite route content. `status_version` increments, so
the representation ETag changes even when the content fingerprint does not.

## Database enforcement

The first migration creates checks for valid state values, region/outcome,
fingerprint shape, positive revisions/status versions, HTTPS entry URLs, and
date ordering. A trigger rejects changes to content and verification timestamps
after a revision leaves draft. Additional triggers reject update/delete on audit
and change events.

Application roles should still receive least-privilege database grants. These
constraints are a final boundary, not a substitute for isolated credentials,
encrypted backups, or access monitoring.
