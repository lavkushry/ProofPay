# ProofPay

> **ProofPay compiles the review queue between 'work submitted' and 'payment released' into executable acceptance checks — and pays only when evidence passes.**

ProofPay is being built for the PayPal AI Hackathon 2026. Its intended workflow connects brief compilation, trusted fixture execution, grounded AI review, correction, and independently guarded sandbox payment.

## Implementation status

The runtime foundation provides a React/TypeScript preview, FastAPI read surfaces, PostgreSQL 17 base identities, and broken/corrected checkout fixtures. Business mutations return `503 WORKFLOW_UNAVAILABLE` while authorization, durable jobs, real verification and guarded payouts are implemented. The preview cannot produce completed payment records.

Actual model integration, PayPal settlement/webhook/cancellation proof, runner job polling, immutable migrations and hosted judge access remain pending. The runner is an optional Compose `verification` profile containing the existing scaffold. Its synthetic outputs are not used by the API.

See [implementation milestones](IMPLEMENTATION_PLAN.md), the [GitHub roadmap](https://github.com/lavkushry/ProofPay/issues/1), and the [API coverage inventory](docs/API_IMPLEMENTATION_STATUS.md). The root `00`–`06` documents define the target product; their contracts do not imply completed implementation.

## Run locally

With Docker and Docker Compose:

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API documentation: http://localhost:8000/docs
- Checkout fixture: http://localhost:8080

Compose initializes the SQL scaffold, seeds base agency/persona records, and waits for API database readiness before starting the web proxy. No provider credentials are needed for this preview. Services bind to localhost; PostgreSQL 17 uses a new `pgdata17` volume, preserving any older PostgreSQL 16 volume. Alembic migrations and full schema/privilege reconciliation are the next milestone.

If a port is occupied, set `PROOFPAY_DB_PORT`, `PROOFPAY_API_PORT`, `PROOFPAY_FIXTURE_PORT` or `PROOFPAY_WEB_PORT` in `.env`. The smoke script accepts matching `--web-url` and `--fixture-url` arguments.

For Python 3.11+ and Node.js 20.19+ or 22.12+ development, run from the repository root in a virtual environment:

```bash
python -m pip install -r backend/requirements.txt -r fixture/requirements.txt
python -m backend.seed
python -m uvicorn backend.app.main:app --reload --port 8000
```

In separate terminals, run `python -m uvicorn fixture.app:app --port 8080` and `cd frontend && npm ci && npm run dev`. The default development database is SQLite; financial/concurrency acceptance requires PostgreSQL. Copy `.env.example` to `.env` only when overriding defaults. The [Vite guide](https://vite.dev/guide/) documents the frontend's Node requirements.

## Validate changes

```bash
python -m pytest -q
python -m compileall -q backend fixture runner scripts
python scripts/api_inventory.py --check
```

In `frontend/`, run `npm ci`, `npm run build`, and `npm audit --audit-level=moderate`. With Compose running, `python scripts/smoke_test.py` checks PostgreSQL readiness, seeded identity, nginx API routing and SPA fallback, fixtures, and the delivery hold. GitHub Actions runs these checks and a fresh-Compose smoke job.

Python dependency ranges live in each service's `requirements.in`; compiled `requirements.txt` files pin resolved versions. Regenerate with `uv pip compile SERVICE/requirements.in --python-version 3.11 --output-file SERVICE/requirements.txt`. Keep the Playwright image tag aligned with the runner's pinned package.

## Payment boundary

The API configuration contains no PayPal or recipient-decryption credentials. The transport adapter loads separate `.env.executor` settings when explicitly instantiated and enforces the sandbox host and six-operation allowlist. Missing credentials raise an unavailable error; provider failures remain failures. The API never instantiates this adapter. Its future executor worker still requires persistent attempt identity, independent guards and item reconciliation before dispatch is enabled.

Keep real credentials outside source control, model context, fixture/runner containers and logs. Test doubles establish local behavior only; genuine sandbox identifiers and evidence are required for the completed demo case.

## Target demo and license

The planned D01–D12 journey is a 175-second owner/contractor demonstration: approve three checks, expose a real contradiction at a 320px viewport, resubmit a corrected artifact, reconcile genuine payout item success, inspect the linked receipt, and prove replay creates no duplicate payment. It remains a release gate in the implementation plan.

MIT licensed. See [LICENSE](LICENSE).
