# Validation and kill criteria

Passing technical tests does not prove that the product deserves to exist. The
following experiments are pre-registered so weak results cannot be reframed as
success after the fact.

## Claim 1: one generic graph schema represents materially different exits

Kill criterion: any of an ordinary web maze, deceptive loop, phone-only path,
or regional/platform variant requires a service-specific schema field or yields
the wrong hand-labeled route.

Cheapest test: encode at least five adversarial fixtures, JSON round-trip them,
validate all references, and compare computed paths with labels.

Current result: a temporary Python spike encoded five variants, returned all
five expected paths, survived JSON serialization, and rejected a dangling edge.
This supports the schema direction but is not production validation. ER-002 and
ER-003 must reproduce it in the repository.

## Claim 2: developers need the graph rather than another directory

Kill criterion: after seeing live example data and a sandbox, none of three
qualified design partners will integrate it or provide a concrete written
integration commitment.

Cheapest test:

1. Interview five developers across subscription finance, privacy/browser
   tooling, and consumer advocacy.
2. Show the same five real routes as prose and as API graphs.
3. Ask them to complete a narrow integration task with the sandbox.
4. Record behavior, missing fields, time, and whether they keep the key.

Pass line: at least two completed sandbox integrations, or one committed paid
pilot. Compliments, waitlist signups, and hypothetical willingness do not pass.

## Claim 3: verified freshness is operationally sustainable

Kill criterion: the median verification effort or observed change rate implies
that a 25-service catalog cannot be kept within its review policy by the
available builder time or plausible pilot revenue.

Cheapest test: manually verify five services twice, then recheck weekly for four
weeks. Record active minutes, blocked routes, differences, and ambiguity.

Pass line: a written staffing/cost model based on those measurements can keep
25 routes within policy with at least 30% capacity margin. Do not automate around
a failed process before understanding why it failed.

## Claim 4: the playful reference client attracts attention

Kill criterion: fewer than 50% of recruited testers finish one level, fewer than
25% voluntarily play another, or fewer than 10% share/challenge someone.

Cheapest test: build three link-free levels and test with 30 people outside the
project team. Measure events; do not substitute stated enjoyment for behavior.

All three thresholds must pass. If the API demand test passes but the game test
fails, keep the API and replace the growth wedge. If the game passes but API
demand fails, do not pretend entertainment engagement validates the backend.

## Claim 5: route instructions help users complete the intended task

Kill criterion: more than one of five blinded users following a verified route
cannot reach the service's cancellation-confirmed state without outside help,
excluding a documented service outage.

Cheapest test: five moderated sessions across at least three routes. Observe
without rescuing, record the failed node, and never collect credentials.

Pass line: at least four of five reach confirmation; every failure creates a
schema, wording, variant, or freshness investigation.

## Privacy falsifier

Before any public submission release, inject names, emails, phone numbers,
addresses, member IDs, payment fragments, tokens, and long free text into all
accepted fields.

Pass line: disallowed values are rejected or quarantined, public route and
challenge payloads contain zero planted values, and logs contain zero secret
values. Any leak blocks release.

## Decision record

At the end of each experiment, commit:

- Date and exact tested build/revision
- Recruitment and exclusions
- Raw aggregate counts
- Pre-registered threshold
- Deviations and failures
- Decision: hold, revise, or retract the claim

Never delete failed experiments from history.
