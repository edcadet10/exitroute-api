# Security policy

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/edcadet10/exitroute-api/security/advisories/new).
Do not open a public issue for a suspected vulnerability and do not include real
account credentials, cookies, personal data, or private cancellation evidence.

Include the affected commit/version, prerequisites, a minimal fictional proof of
concept, security impact, and any suggested mitigation. Maintainers should
acknowledge a complete report within 3 business days, provide an assessment or
request for details within 7 business days, and coordinate disclosure after a
fix is available. These are response goals, not a bounty promise.

## Supported versions

Until the first stable release, only the latest commit on `main` receives security
fixes. Published releases will document any expanded support window here.

## Security boundaries

ExitRoute never needs consumer service credentials. Payloads or issues asking it
to store passwords, session cookies, payment data, or authenticated screenshots
are out of scope and should be removed, not accommodated.

The repository's controls include keyed API-key digests, production configuration
guards, scoped credentials, immutable publication/audit records, PII filtering,
transactional outbox delivery, DNS/IP validation, pinned outbound connections,
TLS hostname verification, no redirects, bounded retries, locked dependencies,
CodeQL, dependency review, and vulnerability auditing.

Self-hosters remain responsible for TLS termination, network isolation, secret
storage, least-privilege database roles, encrypted backups, monitoring, timely
updates, and the legality and accuracy of route data they publish.
