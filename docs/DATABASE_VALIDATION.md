# Database foundation validation

Date: 3 October 2026. Scope: the migrations/integrity/roles change under
[issue #5](https://github.com/lavkushry/ProofPay/issues/5), part of M1/#3.

## Executed checks

| Check | Result |
| --- | --- |
| Deployment Python 3.11, pinned dependencies, PostgreSQL 17 | 67 pytest checks passed: 22 regression/unit checks and 45 PostgreSQL checks |
| Fresh PostgreSQL upgrade and repeat upgrade | All 36 tables; ORM types/keys/indexes align with migrated metadata |
| Supported upgrade | Versioned and exact unversioned PR #4 baseline; IDs/balances preserved; administrator-owned tables transferred to migration owner |
| Unsupported/invalid upgrade | Partial schema and invalid existing rows reject and roll back without losing data or advancing the revision |
| Authority and source integrity | Scoped tenant/current pointers; approved mandate/check immutability; append-only audit/source; bounded evidence bytes |
| Financial identity | One obligation, concurrent initiation with one winner, one unresolved/successful attempt, immutable attempts, once-only consistent ledger phases and same-attempt proof FK |
| Webhook quarantine | Unverified input cannot occupy canonical dedup; verified source identity remains immutable |
| Runtime role logins | API denies financial writes, ciphertext reads, schema creation, truncation, migration-role switching and paid-task insertion/update; executor cannot change funding or approved terms |
| Ordinary API persistence | Redacted ORM reads, audit/outbox inserts and initial zero-balance obligation succeed under restricted API login |
| Compose | Provision/migrate/seed one-shot jobs exit successfully; API starts with its restricted login; web/proxy/SPA/fixture/delivery-hold smoke passes |
| Repository checks | Python compilation, API inventory and diff whitespace checks pass |

Commands are documented in [the migration guide](DATABASE_MIGRATIONS.md).
Validation used isolated PostgreSQL databases and the actual deployment Python
image. A Starlette/httpx deprecation warning remains; no test failed.

## Acceptance limits

These tests use explicitly labeled business/model/provider doubles and do not
prove actual model inference, browser evidence grounding or PayPal sandbox
settlement. Database grants establish which service can write financial data;
M5 must establish the actual guarded provider transaction.

Sessions/CSRF/scoped persona authorization, canonical command execution,
transactional outbox workers, lease fencing and shared agency transaction
ordering remain the next change under #3. Existing unfinished workflow mutations
remain unavailable. M0 provider/model/hosted-runner gates and full M1 acceptance
remain pending. [AGENTS.md](../AGENTS.md) is preserved unchanged.
