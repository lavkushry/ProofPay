# PostgreSQL migrations and runtime roles

Alembic is the schema authority. API startup and base seeding never create or
alter tables. PostgreSQL 17 is required; SQLite remains a unit-test double.

## Fresh local startup

From the repository root, run `docker compose up --build`. The dependency order
is PostgreSQL → administrative role provisioning → migration and idempotent
base seed → API → web. Provisioning and migration containers exit on success;
the API health check requires the current Alembic revision. The runner receives
no database credentials.

Local example passwords in Compose and `.env.example` are development values.
For deployment, use generated secrets and URL-encode passwords in connection
URLs. Run administrative provisioning and migration as separate one-shot jobs;
only the API connection belongs in the API environment. Supply executor
credentials only to the future executor worker.

## Role boundaries

| Role | Authority |
| --- | --- |
| `proofpay_migrator` | Owns schema/tables/functions; applies revisions and base seed |
| `proofpay_api` | Reads redacted projections; writes domain/audit/outbox records; creates an obligation with default zero balances |
| `proofpay_executor` | Allocates attempts, posts ledger entries, records provider observations, verifies webhooks and changes financial projections |

Runtime roles have no schema creation, role membership, deletion, truncation,
funding-limit adjustment or migration authority. API access excludes protected
receiver, request and response ciphertext. Approved sources and audit rows are
immutable even for the executor. Grants establish the writer boundary; actual
provider matching and payout eligibility remain M5 application responsibilities.
This follows PostgreSQL's [privilege model](https://www.postgresql.org/docs/17/ddl-priv.html).

For a separately provisioned database, configure `ADMIN_DATABASE_URL` and the
three `PROOFPAY_*_PASSWORD` variables, then run
`python -m backend.provision_db`. The administrator must be able to create roles
and assign database/schema ownership. Runtime roles with existing memberships
are rejected for operator review. Then configure `MIGRATION_DATABASE_URL` with
the migration role and run `python -m backend.migrate`. Alembic's configuration
also supports `alembic -c backend/alembic.ini upgrade head` with that variable;
the wrapper additionally serializes migration runs with an advisory lock.

## Upgrade the merged runtime foundation

Back up and verify the database before upgrading. Existing `pgdata17` volumes
are preserved. A normal migration intentionally refuses an unversioned schema.

1. Run the new provisioning job: `docker compose run --rm provision`.
2. In an administrative shell, set `MIGRATION_DATABASE_URL` to the **current
   table owner or administrator** connection and run
   `python -m backend.migrate --adopt-runtime-baseline`.
3. Start the stack normally with `docker compose up --build`.

Adoption compares every baseline table's columns/types/defaults, primary and
scoped foreign keys, checks, uniqueness, indexes and triggers with a temporary
reference schema. Only the exact PR #4 initialization schema is supported.
After validation it transfers those 36 tables to `proofpay_migrator`, switches
to that role, stamps the baseline, and applies all revisions atomically. Actor
IDs, allowance counters and business history retain their original values.
Existing rows that violate new constraints abort the whole upgrade without
rewriting, dropping or fabricating history.

Partial initialization and databases created by the old ORM are unsupported.
Preserve their backup and inspect them before a reviewed data migration; do not
stamp them blindly. Destructive downgrades are disabled. Recover using a verified
backup or a reviewed forward migration.

## Acceptance checks

Install `backend/requirements.txt`, then point `PROOFPAY_TEST_DATABASE_URL` at an
**isolated PostgreSQL server administrator connection**, never a business server:

```sh
python -m pytest -q -m postgres
python -m pytest -q -m 'not postgres'
```

The PostgreSQL suite provisions cluster-scoped test role passwords and creates
and drops its own randomly named test databases.
It exercises fresh/versioned/unversioned upgrades, rollback, mapping alignment,
tenant/current-pointer constraints, immutable authority/history, concurrent
attempts, once-only ledger phases, evidence limits, webhook quarantine and
actual API/executor logins. Business, AI and provider inputs are explicit test
doubles; this suite makes no real sandbox-payment or model claim.

Sessions, command execution, leased workers and guarded payouts remain held
until their following implementation changes satisfy the corresponding gates.
