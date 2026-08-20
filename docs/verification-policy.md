# Verification, freshness, and safety policy

Trustworthy freshness is the hard part of this product. This policy is part of
the API contract, not an internal editorial suggestion.

## Allowed material

Publish only semantic interface facts needed to understand an exit flow:

- Public service name and exact official domain
- Region, platform, and cancellation outcome
- Starting URL where publicly shareable
- Screen/node purpose
- Choice labels and their behavioral effect
- Required non-secret prerequisites such as "billing owner must perform this"
- Verification timestamp, review date, and confidence state

Never accept or publish usernames, names of account holders, email addresses,
phone numbers, addresses, member/account numbers, payment fragments, passwords,
one-time codes, cookies, tokens, or private support transcripts.

## Verification procedure

For each candidate revision:

1. Begin from a clean browser session and the recorded region/platform.
2. Traverse the flow without entering real personal information into project records.
3. Record nodes, choice labels, effects, handoffs, and the cancellation-confirmed state.
4. Canonicalize and validate the graph; compute best route and friction.
5. Repeat in an independent session. Prefer a second verifier for the final 25-route set.
6. Resolve discrepancies or publish an explicit unavailable/uncertain state.
7. Record an evidence summary, verifier, timestamp, and next review date privately.

The project must never claim a cancellation succeeded without observing the
service's own confirmation state. A phone handoff is labeled as a handoff until
the downstream confirmation is independently verified.

## Confidence states

- `verified`: two consistent verification sessions and review date not passed
- `provisional`: one successful session or a documented unresolved variant
- `stale`: review date passed or credible change report awaiting review
- `unavailable`: no reproducible cancellation path for the requested variant
- `withdrawn`: unsafe, incorrect, disputed, or no longer suitable for publication

Clients receive the state directly. The API never silently falls back from a
verified regional/platform variant to a different one.

## Freshness

- Initial review interval: 30 days for all MVP routes.
- Immediately mark a route stale after a credible report of a material change.
- A scheduled job marks overdue revisions stale; it does not rewrite timestamps.
- Publish all changes through an ordered change feed.
- Measure verification minutes per route and change frequency. These determine
  whether the catalog can grow sustainably.

Thirty days is a pilot policy, not a claim that flows remain correct for thirty
days. Tighten or relax it only using observed change and verification data.

## Observation moderation

Observation input is structured and bounded. It may report:

- Entry URL changed
- Choice label changed
- Step added or removed
- New loop or retention offer
- New offline handoff
- Cancellation terminal missing
- Region/platform mismatch
- Other, with short bounded explanation

Submission creates a moderation item only. No reporter can directly update a
published route. Apply idempotency, rate limits, duplicate grouping, automated
PII-pattern rejection, and human review.

## Evidence and screenshots

The MVP stores no raw screenshots. If screenshots become necessary, stop and
complete a separate design covering consent, access, encryption, automated and
human redaction, retention/deletion, legal review, and incident response before
collecting any image.

## Corrections and disputes

- Mark a credible disputed revision stale while investigating.
- Publish corrections as new revisions with a public change summary.
- Preserve the audit trail and privately document the reason.
- Provide an abuse/contact channel for services and users.
- Withdraw data immediately when publication could cause harm; investigate later.
