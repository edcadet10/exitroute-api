# ExitRoute API

ExitRoute is a backend-first product for factual, current, machine-readable
instructions for leaving digital services. It models cancellation flows as
versioned decision graphs, calculates the lowest-friction verified route, and
exposes the same data to finance apps, browser extensions, consumer tools, and
playful clients.

> Status: planning and contract validation. No production service or real-brand
> route data exists yet.

## Why this should exist

An FTC-led 2024 review of 642 subscription websites and apps found that nearly
76% displayed at least one possible dark pattern and nearly 67% displayed more
than one. Most existing developer APIs can cancel only subscriptions controlled
by that API's merchant. Consumer-facing directories generally expose a link,
difficulty, and prose notes—not a versioned graph an independent application can
reliably consume.

ExitRoute's product is the data infrastructure. A daily cancellation
"speedrun" is the public reference client and growth loop: it makes the data
interesting, attracts reports when flows change, and gives developers a working
integration to copy.

## MVP

The first release is intentionally narrow:

- Subscription cancellation only
- United States and web flows only
- 25 manually verified services
- Read API for current routes and revision history
- Structured, PII-free change observations
- A daily challenge endpoint backed by the same route graph
- API keys, rate limits, audit events, and freshness metadata

It will **not** log into user accounts, click buttons, cancel on anyone's behalf,
store credentials, scrape authenticated pages, or publish raw screenshots.

## Example

```http
GET /v1/services/example-stream/exit-route?region=US&platform=web
```

```json
{
  "service": {"slug": "example-stream", "name": "Example Stream"},
  "outcome": "cancel_subscription",
  "variant": {"region": "US", "platform": "web"},
  "revision": 3,
  "status": "verified",
  "verified_at": "2026-08-20T14:30:00Z",
  "review_due_at": "2026-09-19T14:30:00Z",
  "entry_url": "https://example.com/account",
  "best_route": ["manage", "continue", "decline-offer", "confirm"],
  "friction": {
    "screens": 4,
    "retention_offers": 1,
    "loops": 0,
    "offline_handoff": false,
    "effort_score": 7
  }
}
```

The full response includes the nodes and choices referenced by `best_route`.
See [openapi.yaml](openapi.yaml) for the initial contract.

## Repository map

- [PLAN.md](PLAN.md) — staged implementation plan and definition of done
- [BACKLOG.md](BACKLOG.md) — ordered implementation tickets with acceptance criteria
- [docs/architecture.md](docs/architecture.md) — components, boundaries, and scaling triggers
- [docs/data-model.md](docs/data-model.md) — storage model and graph invariants
- [docs/verification-policy.md](docs/verification-policy.md) — evidence, moderation, freshness, and privacy rules
- [docs/validation-plan.md](docs/validation-plan.md) — experiments and kill criteria
- [docs/risks.md](docs/risks.md) — product, legal, security, and operational risks
- [openapi.yaml](openapi.yaml) — contract-first API sketch
- [examples/exit-route.json](examples/exit-route.json) — validated example payload

## Start here

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_contract.py
```

Implementation starts only after the contract test passes. Product expansion
starts only after the pilot gates in `docs/validation-plan.md` pass.

## Evidence used in this plan

- [FTC subscription dark-pattern review](https://search.ftc.gov/news-events/news/press-releases/2024/07/ftc-icpen-gpen-announce-results-review-use-dark-patterns-affecting-subscription-services-privacy)
- [JustDeleteAccount API](https://www.justdeleteaccount.com/api.php), the closest directory-style API found
- [Cancel Atlas](https://cancelatlas.com/), an adjacent policy-scoring/open-data project
- [Stripe subscription cancellation](https://docs.stripe.com/billing/subscriptions/cancel), illustrating the merchant-owned API category
- [FastAPI features](https://fastapi.tiangolo.com/features/)
- [PostgreSQL JSONB documentation](https://www.postgresql.org/docs/current/datatype-json.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [RFC 9457 Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)

## Working decisions

The project name, visual identity, hosting provider, pricing, and public license
remain open. The initial repository should stay private while the idea and data
rights are evaluated.
