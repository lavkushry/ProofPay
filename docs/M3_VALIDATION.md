# Delivery, runner and evidence validation

Date: 3 October 2026. Scope: [M3 / issue #13](https://github.com/lavkushry/ProofPay/issues/13).

## Implemented behavior

Assigned contractors submit one reviewed artifact against current unexpired
approved authority. Capture records sequence/predecessor, frozen digests and
three approved checks, then queues a verification job in the same command
transaction. Both submission aliases share replay identity. Payment initiation
blocks replacement.

A separately authenticated runner claims renewable leases and executes eight
trusted templates. It fetches actual fixture bytes over bounded HTTP, verifies
their reviewed digest, and renders those verified bytes in Chromium. Browser
contexts use a 320×640 viewport; other requests, websockets, downloads and
service workers are denied. Each browser check records a genuine screenshot.
API checks record actual status and response observations.

Completion verifies lease ownership, exactly three checks, original provenance,
measured outcomes, timestamps, JSON/PNG limits and decoded PNG dimensions.
PostgreSQL stores immutable results, bytes and a hashed manifest. Downloads
verify the manifest, lineage, rows and exact bytes. Identical completion replay
deduplicates; conflicting data rejects. Superseded delivery/mandate completions
remain inspectable history without changing current evidence.

## Actual execution evidence

The acceptance cases start real API/fixture HTTP servers, launch the actual
Docker polling daemon, execute Chromium/HTTP checks and ingest/download evidence
through the API using the restricted PostgreSQL role.

| Artifact | C01 | C02 | C03 |
| --- | --- | --- | --- |
| `checkout_mobile_broken` | fail | pass | pass |
| `checkout_mobile_fixed` | pass | pass | pass |
| `checkout_api_broken` | fail | fail | fail |
| `checkout_api_fixed` | pass | pass | pass |
| `checkout_keyboard_broken` | fail | fail | fail |
| `checkout_keyboard_fixed` | pass | pass | pass |

The broken responsive document measures **544px scroll width at 320px**, giving
224px overflow. The corrected document measures 320px with no overflow.
Keyboard failures come from actual Tab reachability, Enter activation and
accessible-name observations. API failures come from actual status, schema and
total observations. Six JSON reports and twelve decoded, hash-verified PNGs are
saved under `artifacts/verification/` and uploaded by CI.

Unedited C01 evidence: [broken](screenshots/verification-mobile-broken.png) and
[corrected](screenshots/verification-mobile-fixed.png).

## Acceptance checks

- Full suite: 155 checks pass, including 37 unit/fixture/provider checks and 118
  PostgreSQL checks; six PostgreSQL cases execute the actual container runner.
- Delivery scope, replay, predecessor selection, approved authority, payment
  history, stale completion and concurrent completion pass.
- Twelve malformed/tampered completion cases reject without evidence. Corrupted
  stored bytes reject on bundle and artifact reads. Immutable inputs/manifests
  reject direct changes.
- Recovery, heartbeat, old tokens, retry exhaustion and expiry during ingestion
  pass. The final ownership fence rolls back all evidence when a lease expires.
- Fresh/repeated/legacy migrations and ORM alignment pass with
  `0005_verification`; existing authority and financial grant tests pass.
- Actual Compose startup/session/proxy/fixture smoke passes. The runner reaches
  API/fixture while database and public egress probes fail. It runs as `pwuser`
  with a read-only filesystem, dropped capabilities, no additional privileges,
  768MiB memory, one CPU and 256 processes.

## Reproduce

Set `PROOFPAY_TEST_DATABASE_URL` to an isolated PostgreSQL 17 administrator
connection. The suite provisions test roles and creates/drops its own databases.

```sh
docker build -f runner/Dockerfile -t proofpay-m3-runner .
PROOFPAY_RUNNER_BROWSER_TESTS=1 python -m pytest -q
python -m compileall -q backend fixture runner scripts
python scripts/api_inventory.py --check
docker compose --profile verification up --build -d --wait --wait-timeout 180
python scripts/smoke_test.py
python scripts/runner_isolation.py
```

Override `PROOFPAY_RUNNER_IMAGE` if using another image tag. Evidence artifacts
are ignored by Git; the two linked PNGs are retained as reviewable proof.

## Limits and next milestone

Compiler/model, recipient ciphertext and authority setup in these tests are
explicit doubles. Actual execution, service-token polling, browser/HTTP
observations and PostgreSQL storage/read-back are real. Local acceptance uses
Python 3.14; deployment and CI use Python 3.11. The existing Starlette/httpx
deprecation warning remains.

Completed current evidence keeps the task `verifying` with
`REVIEW_NOT_IMPLEMENTED`; failed/error checks add their own hold reason. This
slice creates no review decision or payout attempt. M4 must consume actual
stored evidence for grounded review and correction. Genuine provider evaluation,
protected recipient provisioning, payouts, hosted runner operation, the complete
EV journeys and formal thirty-run NFR timing measurements remain open.
