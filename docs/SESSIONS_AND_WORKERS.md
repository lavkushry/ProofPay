# Sessions, commands and workflow worker

## Configuration and access

Copy `.env.example` for direct API development. Configure a session HMAC key of
at least 32 characters and distinct nonempty access codes for the personas you
want to enable. An ordinary code permits its single persona; a judge code
permits owner, Maya and Leo. Empty/duplicate codes or a missing key fail closed.
The base seed supplies these identities without financial or model evidence.

Compose explicitly uses public local example codes and HTTP cookies. For
deployment, generate private codes/key, set `SESSION_COOKIE_SECURE=true`, serve
HTTPS and configure exact `CORS_ORIGINS`. Insecure cookies are rejected outside
development/test. The worker receives the restricted API database login and no
session, model, PayPal, recipient-decryption or migration credentials.

`POST /api/session` accepts `{access_code, persona}`. The server stores only the
opaque cookie hash, uses HttpOnly/SameSite=Lax cookies, and returns the session
CSRF token. `GET /api/session` restores identity; `DELETE /api/session` revokes it.
Both deletion and `POST /api/judge/role` require `X-CSRF-Token`. Judge switching
revokes the old cookie, rotates cookie/CSRF, retains original principal and
expiry, and records the effective actor. Contractor reads follow current
assignment; inaccessible/foreign resources return 404.

## Commands and locks

Domain POSTs require CSRF and a UUID `Idempotency-Key`. Reuse that key for a
retry with the same validated body. Receipts are scoped to agency, original
principal, effective actor and canonical command family. Replay reauthorizes
before returning the original status/body; changed data returns
`409 IDEMPOTENCY_CONFLICT`. Both delivery submission aliases share a family.

Commands use the shared workspace advisory transaction try-lock, then agency,
task/obligation, mandate version and attempt/item row order where applicable.
A busy dispatcher returns retryable `409 WORKSPACE_BUSY`. Domain writes, audit,
outbox and the final unique receipt commit together. External I/O belongs after
commit; completion callbacks perform database work only.

## Worker and current handlers

Compose starts `python -m backend.worker`. Claims use short `FOR UPDATE SKIP
LOCKED` transactions, random tokens, 120-second leases and 20-second heartbeats.
Unexpired ownership fences stage writes, retries and completion. Expired work
redelivers with a new token; accepted stage outputs persist unchanged. After
three claims, exhausted work fails. Unsupported handlers hold visibly.

The sole handler records an already captured brief, validates its task/revision
lineage and appends completion audit. `GET /api/jobs/{id}` exposes authorized
status without payloads/tokens. A done job means draft capture completed; it
does not establish compilation, passing evidence or payment.

Base seeding has no trusted manifest, so new `/api/briefs` capture returns 503
until M2 configures the catalog. Compilation/approval, new delivery processing,
judge reset/replay and financial dispatch remain held. Runner/service identity,
AI stages, payout execution and operational worker readiness are later gates.
