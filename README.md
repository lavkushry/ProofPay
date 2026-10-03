# ProofPay

> **ProofPay compiles the review queue between 'work submitted' and 'payment released' into executable acceptance checks — and pays only when evidence passes.**

ProofPay is being built for the PayPal AI Hackathon 2026. Its intended workflow connects brief compilation, trusted fixture execution, grounded AI review, correction, and independently guarded sandbox payment.

## Implementation status

The foundation provides PostgreSQL 17 migrations and integrity constraints, restricted runtime roles, authenticated owner/contractor sessions, judge impersonation with preserved principal identity, atomic command receipts, and a leased workflow worker. The React preview uses server sessions. Broken/corrected checkout fixtures are available.

Brief capture and revisions use the seeded immutable fixture catalog. Durable structured compilation supports OpenAI, Gemini and OpenRouter. Canonical mandate APIs draft versions, approve an exact digest, freeze three validated checks and recipient/payment terms, and supersede prior authority while preserving the payment obligation and history. Compilation requires configured provider access; approval requires a confirmed protected recipient binding, which base seeding does not fabricate. See [mandate validation](docs/MANDATE_VALIDATION.md).

Delivery verification, reset/replay and payouts remain held. Actual model evaluation, sandbox settlement/webhook/cancellation proof, runner polling and hosted judge access are pending. The optional `verification` profile contains the runner scaffold; its synthetic outputs are not used by the API.

See [implementation milestones](IMPLEMENTATION_PLAN.md), the [GitHub roadmap](https://github.com/lavkushry/ProofPay/issues/1), and the [API coverage inventory](docs/API_IMPLEMENTATION_STATUS.md). The root `00`–`06` documents define the target product; their contracts do not imply completed implementation.

## Run locally

With Docker and Docker Compose:

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API documentation: http://localhost:8000/docs
- Checkout fixture: http://localhost:8080

Compose provisions separate database roles, applies Alembic migrations, preserves base identities/history, then starts the API, workflow worker and web proxy. No provider credentials are needed. Services bind to localhost; PostgreSQL 17 uses `pgdata17`, preserving any older PostgreSQL 16 volume. Upgrade an unversioned PR #4 database using the [migration guide](docs/DATABASE_MIGRATIONS.md).

Sign in with `local-judge-access` for owner/Maya/Leo switching, or use `local-owner-access`, `local-maya-access`, or `local-leo-access` with the corresponding starting persona. These public codes and the Compose session key are local development examples. Replace them for deployment and require HTTPS/Secure cookies. See [session and worker operations](docs/SESSIONS_AND_WORKERS.md).

If a port is occupied, set `PROOFPAY_DB_PORT`, `PROOFPAY_API_PORT`, `PROOFPAY_FIXTURE_PORT` or `PROOFPAY_WEB_PORT` in `.env`. The smoke script accepts matching `--web-url` and `--fixture-url` arguments.

For Python 3.11+ and Node.js 20.19+ or 22.12+ development, run from the repository root in a virtual environment:

```bash
python -m pip install -r backend/requirements.txt -r fixture/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
```

First start the Compose database/provisioning/migration services. Copy `.env.example` to `.env` for API session configuration; the default database connection uses the restricted PostgreSQL API role. For Vite, add `http://localhost:5173` to `CORS_ORIGINS`. In separate terminals, run `python -m uvicorn fixture.app:app --port 8080` and `cd frontend && npm ci && npm run dev`. SQLite is a unit-test double. The [Vite guide](https://vite.dev/guide/) documents frontend Node requirements.

## Validate changes

```bash
python -m pytest -q
python -m compileall -q backend fixture runner scripts
python scripts/api_inventory.py --check
```

In `frontend/`, run `npm ci`, `npm run build`, and `npm audit --audit-level=moderate`. With Compose running, `python scripts/smoke_test.py` checks readiness, real sessions/CSRF/persona/logout, nginx routing, fixtures and the delivery hold. GitHub Actions also runs PostgreSQL acceptance and actual Chromium validation, uploading screenshots. PostgreSQL tests require an isolated administrative test connection; see the [validation report](docs/WORKFLOW_VALIDATION.md).

Python dependency ranges live in each service's `requirements.in`; compiled `requirements.txt` files pin resolved versions. Regenerate with `uv pip compile SERVICE/requirements.in --python-version 3.11 --output-file SERVICE/requirements.txt`. Keep the Playwright image tag aligned with the runner's pinned package.

## Payment boundary

The API configuration contains no PayPal or recipient-decryption credentials. The transport adapter loads separate `.env.executor` settings when explicitly instantiated and enforces the sandbox host and six-operation allowlist. Missing credentials raise an unavailable error; provider failures remain failures. The API never instantiates this adapter. Its future executor worker still requires persistent attempt identity, independent guards and item reconciliation before dispatch is enabled.

Keep real credentials outside source control, model context, fixture/runner containers and logs. Test doubles establish local behavior only; genuine sandbox identifiers and evidence are required for the completed demo case.

## Target demo and license

The planned D01–D12 journey is a 175-second owner/contractor demonstration: approve three checks, expose a real contradiction at a 320px viewport, resubmit a corrected artifact, reconcile genuine payout item success, inspect the linked receipt, and prove replay creates no duplicate payment. It remains a release gate in the implementation plan.

MIT licensed. See [LICENSE](LICENSE).
