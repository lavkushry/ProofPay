# Mandate approval validation

The canonical APIs implement the authority slice of M2 (FR-03, FR-19, FR-20,
FR-22 and FR-30). Delivery verification and financial execution remain subsequent
milestones. The transitional `/api/v1/mandates/approve` route remains held; callers
must use the version-specific canonical route.

## Commands and reads

All mutations require an owner session, CSRF token and UUID `Idempotency-Key`.
Commands atomically persist the result, audit event, durable recording job and
receipt. Replaying the same key returns the saved response; changed data conflicts.

| Operation | Route | Inputs |
| --- | --- | --- |
| First draft | `POST /api/mandates` | Task, current brief revision, ready compilation, payment terms |
| Replacement draft | `POST /api/mandates/{id}/versions` | Revision, compilation, terms, expected current version (nullable) |
| Approval | `POST /api/mandates/{id}/versions/{version_id}/approve` | Exact draft digest and expected current version (nullable) |
| History | `GET /api/mandates/{id}` | Latest 50 permitted versions |
| Version | `GET /api/mandates/{id}/versions/{version_id}` | Original snapshot and current lifecycle |

Drafts do not change current authority. Approval requires a current active task and
brief revision, a completed compilation job and validated immutable compiler
interaction whose source references and input/output digests match. The server
rechecks the three reviewed templates, parameters and authority markers at both
draft creation and approval. Ambiguous, stale, missing or altered sources cannot
establish authority.

The inspected draft pins a confirmed protected recipient binding. A binding change
before approval requires a fresh draft. Directory edits after approval cannot
change the approved hash, receiver binding, terms or display name. Public responses
contain the receiver hash only; runtime API permissions exclude encrypted receivers.
Money uses integer cents internally and exact decimal strings publicly. UTC timestamps
use consistent serialization before hashing. Approval changes the snapshot's status,
check markers and audit actor/time, so its approved digest differs from the draft digest.

## Supersession and financial history

Approval takes the same agency advisory lock as dispatch and updates current
authority atomically. The previous snapshot/checks remain frozen; only its lifecycle
projection becomes superseded. New authority clears current delivery/evidence pointers
and requires evidence bound to the new version. Historical evidence remains stored.

The original obligation, attempts, provider identities and reservations remain intact.
Caps and attempt limits cannot discard already allocated history; successful
obligations reject further approval. The API reads financial history under the shared
agency lock without receiving financial UPDATE grants. Existing executor-owned task
states remain unchanged. Unresolved movement retains its holds plus
`PAYMENT_IN_PROGRESS`; confirmed nonpayment retains its financial state with
`NEW_MANDATE_REQUIRES_DELIVERY` until the later executor/delivery workflow handles it.
Approval recording jobs perform no model, delivery or payment action.

## Reproducible acceptance

```sh
PROOFPAY_TEST_DATABASE_URL=postgresql://ADMIN:PASSWORD@HOST/DB \
  .venv/bin/python -m pytest -q backend/tests/test_mandates.py
.venv/bin/python scripts/api_inventory.py --check
```

Tests use actual PostgreSQL migrations/runtime API permissions and HTTP sessions.
They cover all three families, unauthorized and contractor reads, exact digest/pointer
checks, expiry, source tampering, immutable payload/check enforcement, concurrent
approval and replay, directory edits, supersession, historical evidence, reserved
principal and attempts, successful-payment rejection, lease loss and call budgets.
Authority rows reload after lock acquisition, including when another approval
commits between the initial authorization read and the lock.
Model outputs, encrypted recipient bytes and financial observations are explicit
test doubles. These tests do not establish actual model execution or sandbox payment.

Remaining M2 gates include genuine three-family model/ambiguity evaluations and
deployment recipient provisioning. Product UI migration and delivery/runner/reviewer/
payout workflows remain pending under M3–M7.
