# M1 session and durable-workflow validation

Validated on 3 October 2026 against PostgreSQL 17, actual restricted API/executor
logins, the Compose Python 3.11 runtime, and Chromium in the pinned Playwright
1.63.0 runner image. Relational graph, accepted capture output and callback fault
inputs are explicit test doubles. No actual model or sandbox-payment claim.

81 checks pass: 22 regression/unit and 59 actual PostgreSQL checks, including
14 new session/command/lease acceptance tests. Frontend type/production build,
Python compilation, API inventory, Compose HTTP smoke and Chromium checks pass.

## Reproduce

```sh
python -m pytest -q -m 'not postgres'
# Set an isolated administrative connection, never a business database:
PROOFPAY_TEST_DATABASE_URL=postgresql://ADMIN:PASSWORD@HOST/TEST_DB python -m pytest -q -m postgres
docker compose up --build -d --wait
python scripts/smoke_test.py
docker build -t proofpay-browser-check runner
docker run --rm --network host \
  -v "$PWD/scripts/browser_smoke.py:/app/browser_smoke.py:ro" \
  -v "$PWD/artifacts/browser:/screenshots" \
  proofpay-browser-check python /app/browser_smoke.py
```

PostgreSQL fixtures create/drop randomly named databases and provision
cluster-scoped test passwords. CI runs the same suites and uploads browser
screenshots. Custom local ports require matching smoke/browser arguments;
Compose derives allowed browser origins from `PROOFPAY_WEB_PORT`.

## Acceptance evidence

- Sessions: invalid/wrong-persona codes, secure/HttpOnly cookies, hash storage,
  expiry, revocation, origin/CSRF denial, principal/effective audit and rotation.
- Authorization: owner access, Maya assignment, Leo denial, reassignment denial
  before receipt replay, hidden foreign agency tasks/receipts/jobs, owner-only
  recipients, and job status without source payloads or lease tokens.
- Commands: strict money/expiry/attempt validation, exact replay/status,
  changed-body conflict, principal-scoped keys, concurrent duplicates and busy
  workspace locks. Fault injection bypasses the advisory lock to prove the
  final receipt uniqueness gate rolls back every losing domain/audit/outbox
  write; callback exceptions also roll back completely.
- Leases: locked-row skipping, heartbeats, expired and superseded token denial,
  immutable accepted output, retry exhaustion and unsupported-handler holds.
  Expiry during completion rolls back task mutation and completion audit.
- Crash recovery: a separate worker process commits a capture stage, receives
  SIGKILL, and redelivers after real lease expiry. Its accepted output remains,
  a new token completes the job and exactly one completion audit exists.
- Runtime: preserved PR #6 database upgrades to `0004_command_leases`, seed
  retains history, worker starts, HTTP proxy/session smoke passes, and Chromium
  validates login errors, owner/judge permissions, all three personas, reload,
  logout and unavailable-workflow feedback. Checkout measurements remain actual
  544px broken / 320px fixed at a 320px viewport.

Screenshots: [login](screenshots/session-login.png),
[contractor](screenshots/session-contractor.png),
[owner queue](screenshots/runtime-preview.png),
[workflow hold](screenshots/workflow-hold.png).

## Limits

This accepts M1 infrastructure and draft capture under a configured trusted
catalog. Base seed contains no such catalog. Full canonical read-route parity,
typed client/features, model compilation, approval/supersession, runner jobs,
grounded review, provider execution, reset and hosted operational readiness
remain future milestones. Stage recovery proves persisted output reuse for
capture; it does not prove AI call budgets or provider exactly-once delivery.
