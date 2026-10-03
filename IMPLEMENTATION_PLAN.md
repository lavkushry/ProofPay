# ProofPay implementation plan

Date: 2 October 2026
Scope: the complete MVP, from the existing prototype through hosted demo and submission readiness.
Status: M0 runtime foundation, M1 database/session/worker foundations, M2 trusted-catalog/brief/compiler/mandate APIs, and M3 delivery/runner/evidence APIs are implemented. Actual model evaluation, configured protected recipients, grounded review, payouts and hosted-runner gates remain pending.

Implementation tracking: [MVP roadmap #1](https://github.com/lavkushry/ProofPay/issues/1), [runtime foundation #2](https://github.com/lavkushry/ProofPay/issues/2), [persistence/authorization #3](https://github.com/lavkushry/ProofPay/issues/3), and [database foundation #5](https://github.com/lavkushry/ProofPay/issues/5). PR #6 versions all 36 PostgreSQL tables, enforces source/financial integrity, separates runtime roles and verifies fresh/legacy upgrades. The merged session/worker change adds authenticated personas, CSRF, replay/conflict handling, shared workspace locking, stage persistence and fenced completion. See [workflow validation](docs/WORKFLOW_VALIDATION.md), [database validation](docs/DATABASE_VALIDATION.md), [migration guide](docs/DATABASE_MIGRATIONS.md), [M2 validation](docs/M2_VALIDATION.md), and [API inventory](docs/API_IMPLEMENTATION_STATUS.md).

## 1. Outcome and planning basis

The focused session/worker implementation is tracked in [issue #7](https://github.com/lavkushry/ProofPay/issues/7). M2 validation is recorded in [docs/M2_VALIDATION.md](docs/M2_VALIDATION.md), with provider calls covered by explicit HTTP transports and PostgreSQL worker completion covered by an end-to-end acceptance test.

Exact frozen mandate approval and supersession are tracked in [issue #11](https://github.com/lavkushry/ProofPay/issues/11), with authority, immutable-history and financial-preservation acceptance recorded in [mandate validation](docs/MANDATE_VALIDATION.md).

Actual fixture execution and durable delivery evidence are tracked in [issue #13](https://github.com/lavkushry/ProofPay/issues/13). See [M3 validation](docs/M3_VALIDATION.md) for six real runner cases, immutable read-back, lease fencing and Compose isolation. Completed verification remains held for M4 review.

Deliver the full agency-owner, contractor, and judge journey: compile a brief into three approved checks, freeze payment authority, inspect real execution evidence, request correction when a claim contradicts that evidence, and release a sandbox payout only after independent backend guards pass. A receipt becomes paid only after matching a genuine successful provider item. Replaying the workflow must resolve to the existing financial obligation and attempt.

This plan follows [Project Context](00-PROJECT_CONTEXT.md), [PRD](02-PRD.md), [System Design](03-SYSTEM_DESIGN.md), [API Specification](04-API_SPEC.yaml), [Data Model](05-DATA_MODEL.md), and [AI Layer](06-AI_LAYER.md). Preserve their requirement IDs and acceptance scenarios EV01–EV16. Their historical “documentation only” status predates the code now in this repository; the inspection below describes the current starting point.

The fixed scope remains one agency, one fixture application, two sandbox recipient references, USD, exactly three approved checks per brief, and three families: responsive CSS, API endpoint repair, and keyboard accessibility. Implement all 67 Must requirements. Measure and report NFR-07, the Should performance requirement. FR-38, side-by-side evidence comparison, remains optional.

The six-week schedule comes from the existing project baseline. It is a target, conditional on provider access and team capacity. Verify external submission and hosting requirements during M0 before treating those dates as current external facts.

## 2. Initial prototype inspection and gaps

These historical findings are from source inspection and a Python syntax parse on 2 October 2026, before implementation began. The status above and milestone validation reports record subsequent executed checks and remaining gaps.

| Area | Existing implementation | Work required |
| --- | --- | --- |
| Runtime | Compose, Dockerfiles, Vite, FastAPI and fixture scaffolds exist. `fixture/app.py:77` contains invalid Python syntax. Backend container copies `app/` under `/app` but starts `backend.app.main`, whose package layout is not present there. The production nginx image has no API proxy configuration. | Repair startup, imports, fixture syntax, API routing, configuration, migration and seed order; prove clean-checkout startup. |
| API | 18 route decorators exist, mainly under `/api/v1`; the authoritative contract declares 55 operations on 51 paths using `/api` and `/internal`. | Build an operation-by-operation coverage matrix and implement the contract, including authorization, errors and asynchronous acknowledgements. Counts alone do not establish compatibility. |
| Database | ORM defines 32 tables; SQL initialization defines 36. ORM omits `demo_archives`, `tool_invocations`, `webhook_deliveries` and `webhook_events`. Startup and seeding also use `create_all`. | Establish Alembic as the migration path; reconcile types, constraints, indexes, immutability triggers and runtime grants against the data model. |
| Identity and approval | Session routes return personas without establishing authenticated sessions. Approval ignores the supplied expected digest and uses the agency ID as the approver. | Implement server sessions, roles, CSRF, actor identity, stale-version rejection and immutable approval. |
| Compilation and review | `brief_compiler.py` returns fixed family presets. `evidence_reviewer.py` computes canned verdicts without calling a model or inspecting image bytes. | Add actual structured-output/image inference, semantic validation, durable interaction records and bounded failure handling. |
| Runner and evidence | `runner.py` returns synthetic observations and its main loop only sleeps. Delivery submission independently invents results and inserts mock PNG bytes. Fixture/seed cover only the responsive broken/corrected pair. | Implement leased job polling, real Playwright checks, six artifact versions across three families, and durable artifact-bound evidence. |
| Payments | Delivery submission calls PayPal before persisting the attempt, ignores a failed reservation result, hardcodes the receiver, and writes immediate success with invented item/transaction data. Missing credentials activate simulated responses; simulated webhook verification returns true. | Replace this path with guarded executor transactions, explicit test adapters, genuine item matching, verified webhooks, reconciliation and recovery. |
| Durability | Outbox and command-receipt models exist, but no workflow worker is wired into Compose. Replay returns an existing attempt without exercising normal command processing. Reset only changes demo-run records. | Implement worker leases, command deduplication, dispatch locking, actual replay processing and reset/history protections. |
| Frontend | A large `App.tsx` contains queue/composer/portal/judge and modal UI. Role state is local; success copy depends on the artifact name. Approval mixes mandate and version IDs and submits an arbitrary digest. shadcn/ui and AG Grid are absent from dependencies. | Reuse useful visual structure, split features, consume typed contract data, implement the required components, and derive state/actions from the server. |
| Verification and delivery | No test suite, CI workflow, Alembic configuration, dependency lockfiles or Render manifest was found. | Add checks incrementally with each capability and capture separate local-test, actual-model and real-sandbox evidence. |

## 3. Implementation boundaries

- Keep FastAPI, React/TypeScript, PostgreSQL, Docker Compose, Render, shadcn/ui and AG Grid as specified. Choose and pin one PostgreSQL version for local, CI and hosted use; resolve the current Compose 16 versus data-model 17 baseline during M0.
- Treat `04-API_SPEC.yaml` as the target contract. Move the frontend and backend to its paths and schemas together; any contract change requires a documented reason and matching specification update.
- Keep the API responsible for session-scoped commands, model calls and authorized evidence access. A workflow/executor worker processes durable jobs and alone receives PayPal credentials and recipient-decryption access. The runner has a separate service identity and receives neither database nor provider/model credentials.
- Use PostgreSQL for workflow and financial acceptance tests. SQLite cannot establish the required advisory-lock, concurrent-claim, constraint or privilege behavior.
- Keep deterministic provider/model doubles inside explicitly selected test configurations. Missing real credentials must report an unavailable dependency, never produce successful payment or model records.
- Put execution reports under a proposed `artifacts/validation/` directory, with run metadata and redacted identifiers. Preserve business evidence bytes and audit history in PostgreSQL as specified.

## 4. Milestones and acceptance gates

### M0 — Establish a runnable baseline and prove feasibility

**Owner:** backend/DevOps lead. **Dependencies:** none. **Target:** week 1.

1. Fix fixture syntax and backend import/container layout; make local and container commands use the same package entry points. Add production `/api` routing and frontend refresh handling.
2. Resolve database-version drift, pin dependencies and the compatible Playwright package/image/browser combination, and add repeatable build configuration. Split API, executor and runner secrets/configuration; remove insecure runtime defaults.
3. Disable the prototype's simulated payment-success path for normal runtime. Separate test doubles before supplying actual sandbox credentials.
4. Create a minimal executor-only feasibility harness with sandbox host enforcement, a fixed allowlisted recipient, stable persisted request identity, and redacted observations. After accounts are configured, use it to prove a genuine $1 item success and investigate actual webhook verification and eligible unclaimed cancellation. This spike must not mark application tasks paid or masquerade as the completed seed.
5. Prove that a separately deployed runner can reach the private fixture and upload a real screenshot for durable storage/read-back. Do not assume nested Docker or inbound runner HTTP on Render.
6. Select an available model/provider after proving structured output and actual image input. Verify its current official API contract during integration; the existing `LLM_PROVIDER=gemini` default is not evidence of access or suitability.
7. Record feasibility results, missing access and go/no-go decisions. Assign responsibility for recruiting three agency owners and for judge-period operations.

**Deliverables:** repaired runtime configuration, lockfiles, CI build/syntax skeleton, feasibility harness and redacted report, contract inventory, initial deployment proof.

**Exit gate:** API, frontend and fixture start; runner screenshot survives storage/read-back; genuine payout item and webhook path are evidenced; model access is demonstrated. Record unresolved cancellation coverage explicitly. Provider-dependent work cannot be declared complete if access fails; independent database/UI work may continue.

### M1 — Make persistence and command processing authoritative

**Owner:** backend/data. **Dependencies:** M0 runtime decisions. **Target:** weeks 1–2.

1. Convert the data-model sketches into executable Alembic migrations and matching SQLAlchemy mappings. Replace startup `create_all` and initialization-only SQL as schema authorities. Test both a fresh database and an upgrade from the chosen supported baseline; document handling of prototype data.
2. Implement tenant-scoped foreign keys, approved-source immutability, audit append-only rules, one obligation per milestone, at most one unresolved and one successful attempt per obligation, and one-time ledger posting constraints. Test these at the database boundary.
3. Provision separate migration, API and executor database roles. The API may queue release decisions but cannot create financial attempts/reservations, append provider observations or mark money paid. Keep migration credentials out of runtime services.
4. Implement demo-code session creation, hashed opaque cookies, expiry/revocation, CSRF, scoped owner/contractor access, and judge role switching that preserves principal and effective actor identities. Restrict CORS to configured origins.
5. Add command receipts scoped to agency, original principal, effective persona, command family and idempotency key. Same key/body returns the original response after authorization; a changed body returns `409 IDEMPOTENCY_CONFLICT`. Both contractor submission routes share one command family.
6. Commit domain mutations, audit and outbox records together. Implement short `SKIP LOCKED` claims, random lease tokens, heartbeat, bounded retries and completion fencing. Start with the specified 120-second leases and 20-second heartbeats; tune only with evidence.
7. Implement the shared agency lock and documented row order. API mutations use a transaction try-lock and return `409 WORKSPACE_BUSY` when needed. Network calls do not hold open SQL transactions.

**Primary files:** `backend/app/models.py`, `database.py`, `routers/sessions.py`, `backend/migrations/`; new authorization, command, outbox and worker modules; Compose worker service.

**Exit gate:** migrations work on PostgreSQL; direct unauthorized operations fail; command replay/conflict cases pass; a killed worker can redeliver work without duplicate domain mutations; invalid financial writes are rejected by actual database grants.

### M2 — Implement briefs, actual compilation and frozen authority

**Owner:** backend/AI. **Dependencies:** M1; M0 model feasibility. **Target:** week 2.

Current slice: trusted manifests and six immutable fixture artifacts, owner-scoped
brief revisions, provider-neutral structured compilation for OpenAI/Gemini/OpenRouter,
leased interaction persistence, draft versions, exact digest approval and immutable
supersession are implemented. Approval revalidates compiler lineage and pins a
confirmed recipient binding. PostgreSQL tests exercise all three families with an
explicit model double; real provider evaluation and recipient provisioning remain
deployment-dependent gates. See [mandate validation](docs/MANDATE_VALIDATION.md).

1. Store brief revisions and trusted fixture manifests separately from compilation results. Validate the fixed family/recipient/currency scope at the API boundary.
2. Implement the neutral model adapter, versioned prompts and `propose_checks` schema from `06-AI_LAYER.md`. Resolve templates and parameters against the trusted registry; the model returns no executable code or arbitrary target URLs.
3. Persist model call-start allocations before I/O, interaction lineage, schema errors, usage and outcomes. Permit at most two started calls per stage, including repair, timeout and crash recovery; enforce the proposed 45-second call deadline without hidden SDK retries.
4. Represent ambiguous/unsupported intent explicitly. Approval requires three valid materially appropriate checks; family selection alone cannot stand in for understanding the brief.
5. Implement draft mandate versions, exact expected-digest approval, approval actor/time, expiry, integer-cent amounts and exact decimal serialization. Validate positive USD amounts, recipient binding, principal cap and maximum three business attempts.
6. Freeze approved payloads/checks and pin the protected recipient binding. Supersession creates a new version while retaining the original obligation, attempts, budget history and prior evidence.

**Primary files:** `services/brief_compiler.py`, `routers/briefs.py`, `routers/mandates.py`, `schemas/`; new AI adapter/prompt/validator and mandate services.

**Exit gate:** EV01/EV02 pass, including actual compilation for all three families, ambiguity holds, unauthorized approval, stale digests, immutable snapshots and recipient-directory edits that cannot redirect approved payment.

### M3 — Execute real checks and retain attributable evidence

**Owner:** verification/backend. **Dependencies:** M1; M2 approved-check contract. **Target:** week 3. Fixture/template development can begin during week 2.

**Implemented slice:** contractor-only durable capture, separate runner authentication, renewable/fenced leases, all eight trusted templates, verified HTTP source bytes and actual browser observations, immutable PNG/JSON ingestion, scoped downloads and stale-history preservation. All six artifact cases pass their expected outcomes; broken responsive checkout measures 544px scroll width at a 320px viewport. PostgreSQL corruption/concurrency/lease tests and actual Compose isolation pass. Approval/model/recipient inputs in acceptance are explicit doubles; grounded review and provider/hosting gates remain subsequent work. See [M3 validation](docs/M3_VALIDATION.md).

1. Version the fixture manifest and six allowlisted artifacts: broken/corrected variants for each of the three families. Derive artifact hashes from actual content, not names or placeholder strings. Make API and keyboard defects independently observable.
2. Implement all eight unique trusted templates: overflow, total preservation, keyboard reachability, API status/schema/total, keyboard activation and accessible name. Execute real browser/HTTP observations against the selected artifact. Unknown templates and timeouts must fail or hold, never default to pass.
3. Implement authenticated runner claim/heartbeat/complete endpoints and polling. Bind work to the approved check set, artifact, delivery, mandate and lease. Bound runtime, resources, input size and network targets; use isolated browser contexts and deny arbitrary code/URLs and redirects outside allowed targets.
4. Make delivery submission a short durable acknowledgement that queues verification. Allocate sequence/predecessor and current-delivery pointers under the appropriate lock; deduplicate retries through command receipts.
5. Upload genuine PNG/JSON artifacts and a complete manifest. Validate digests, check IDs, provenance, lease ownership and the specified size limits: 512 KiB per PNG and 64 KiB per JSON result. Store bytes in PostgreSQL and verify them on read-back.
6. Keep older completed jobs inspectable. Before advancing a workflow, compare current delivery and mandate pointers so stale completion cannot authorize release.

**Primary files:** `runner/runner.py`, `runner/contracts.py`, `runner/execution.py`, `fixture_contract/observations.py`, `routers/delivery_commands.py`, `routers/runner_jobs.py`, `routers/verification_reads.py`, and delivery/runner/evidence services.

**Exit gate:** each broken artifact demonstrates its intended defect; each corrected artifact passes its three checks. The responsive case shows actual overflow at 320px using measured dimensions. Corrupted/foreign/missing evidence, lease loss and stale jobs cannot advance payment (EV03/EV04/EV13).

### M4 — Ground review, correction and uncertainty in evidence

**Owner:** AI/backend. **Dependencies:** M2 model runtime and M3 evidence. **Target:** week 3.

1. Build the reviewer packet from the delivery claim, approved checks, stored results and real same-run screenshot bytes. Resolve all references server-side before model access.
2. Implement `inspect_evidence`, `request_correction` and `request_payout` under authenticated job/stage/lease context. Model-supplied payment fields never establish receiver, amount or authority.
3. Validate every per-check result and cited reference against the bundle. A failed executable check forces failure; errors/missing evidence hold; all-pass checks alone do not establish an unambiguous model pass.
4. Persist grounded corrections and resubmissions under the original approved mandate. A valid pass queues release evaluation; it does not directly call PayPal.
5. Allow owner resolution only for uncertainty with all executable checks passing, current evidence, valid citations and a recorded rationale. Preserve the original model verdict. Reject failed-check and stale-evidence overrides.
6. Implement the evaluation harness specified in `06-AI_LAYER.md`: nine canonical compiler evaluations, eighteen reviewer evaluations across six real bundles, and the ambiguity, scope, injection, malformed-reference, stale-job, duplicate and uncertainty cases. Use a payment-request spy, with provider creation disabled for AI evaluation.

**Primary files:** `services/evidence_reviewer.py`; new tool orchestration, correction/resolution routes and `backend/evals/`.

**Exit gate:** EV03–EV05 demonstrate the claim/result/image contradiction, corrected pass, permitted uncertainty resolution and invalid-output holds. The proposed 9/9 and 18/18 canonical gates pass; there are zero unsafe payout requests and no accepted invented references. Publish failed cases as well as successes.

### M5 — Implement guarded payout, reconciliation and recovery

**Owner:** backend/DevOps lead. **Dependencies:** M1 financial schema and M4 eligible decisions. **Target:** week 4. Adapter development can start after M0 using explicit test inputs.

1. Replace direct payment calls in delivery routes with executor-only release evaluation. Implement every guard in PRD section 7.5.1: sandbox/caller, current approval, expiry, frozen financial binding, current evidence, exactly three passing checks, grounded review/resolution, obligation history, attempt limit, both budget controls and persisted identity.
2. In one locked transaction, allocate the numbered attempt, reserve principal, persist the exact encrypted request and stable sender IDs, append audit and queue dispatch. Any guard/reservation failure produces a hold with a permitted next action and no provider create.
3. Before every create send, pin a database connection and acquire the shared session advisory lock. Recheck authority; hold that lock across the bounded HTTP call and outcome persistence, using short SQL transactions around I/O. Release the lock in `finally`. Approval, supersession, delivery replacement and reset use the same lock.
4. Implement the six allowlisted PayPal operations from the project context with strict sandbox host/method/path enforcement, token caching, redaction and bounded errors. Persist observations; never invent missing batch, item, transaction or fee fields.
5. Match provider batch/item identity, sender IDs, pinned receiver, amount and currency to the attempt. Only matched item `SUCCESS` consumes reserved principal and marks the task paid. Batch completion and create acknowledgement remain insufficient.
6. Store webhook raw bytes/headers in quarantine, then let the executor verify authenticity and refresh item status. Canonical event dedup happens only after verification; a forged event using a real event ID cannot suppress a later authentic event.
7. Reconcile processing, on-hold, unclaimed, success, failure, blocked/denied, returned and unknown observations through the specified state machine. Retain reserve while unresolved, post each confirmed disposition once, retain unknown fees as unknown, and never reopen a successful obligation on a stale observation.
8. Retransmit an unknown create only with its exact stored payload/IDs, current authority and the configured cutoff (baseline: earlier of expiry and 24 hours after first dispatch). Otherwise hold and investigate while retaining reserve. A later rejected retransmission does not establish that an earlier unknown send failed.
9. Allocate a new business attempt only after confirmed eligible nonpayment and all guards pass, within the approved maximum. Expired/superseded mandates block new creation while existing transactions continue reconciliation.
10. Implement unclaimed cancellation with refreshed eligibility and race handling. Cancellation acknowledgement alone cannot release principal; reconcile the actual confirmed return or competing success.

**Primary files:** `services/payment_executor.py`, `services/ledger.py`; new release-guard, reconciliation and webhook services/routes; worker and financial database tests.

**Exit gate:** EV06–EV12 pass with appropriate evidence. Actual sandbox success, verified events and eligible cancellation/return require real provider records. Local tests separately cover crashes, duplicate events, lost responses, concurrent dispatch, cap exhaustion, stale authority and unknown states. An unexercised Must provider case remains a release blocker.

### M6 — Complete owner, contractor and judge product surfaces

**Owner:** frontend with backend support. **Dependencies:** M1 sessions and agreed API schemas; evidence/payment screens complete after M4/M5. **Target:** incremental work from week 2, complete in week 5.

1. Generate TypeScript API types from the authoritative contract and build one client for session/CSRF/idempotency, structured errors, `202` acknowledgements and job/status polling. Preserve one idempotency key across retries of the same user action.
2. Split `App.tsx` into session/layout, Work Queue, Brief Composer, Mandate Approval, Evidence Review, Payment/Receipt, Contractor Portal and Judge Workspace features. Install and use the required shadcn/ui and AG Grid components.
3. Build the AG Grid queue with status, holds, contractor, amount, current authority, filters/sorting and server-computed allowed actions. Implement loading, empty, unavailable, stale and validation states.
4. Show compilation progress/clarification and the full frozen terms before approval. Submit the actual version ID and expected digest. Retain usable form state on conflicts/errors.
5. Present claim, actual screenshot, three results, model verdict/citations, correction and permitted uncertainty resolution. Show older evidence with its original identity; prioritize the current run.
6. Present attempts, principal reserved/consumed/available, observed fees, provider status provenance and allowed recovery actions. Build the linked receipt timeline from server records; update to paid only when the server confirms matched success.
7. Make contractor views use assignment-scoped APIs for submissions, correction history and the same receipt state as the owner. Implement judge persona switching through real sessions and display dependency/seed readiness.
8. Verify keyboard navigation, focus restoration, semantic labels, status text beyond color, safe rendering of claims/model content, and responsive layouts. Replace alert-only and artifact-name-based success messages with persisted workflow state.

**Primary files:** `frontend/src/App.tsx`, new `frontend/src/features/`, `components/`, `lib/api/`, generated contract types and browser tests; author `08-UI_SPEC.md` alongside implementation.

**Exit gate:** EV13/EV14 pass in clean owner, both contractor and judge sessions. All required screens handle their allowed actions and failures; direct API access enforces the same permissions as the UI.

### M7 — Make seeds, replay, reset and deployment operational

**Owner:** backend/DevOps with frontend support. **Dependencies:** M5; M6 for full judge acceptance. **Target:** week 5, with hosting work beginning in M0.

1. Replace the seed script with idempotent base-data setup, protected confirmed recipient bindings and a fresh mid-flow case created through actual compilation/approval. Leave a failed compilation visibly pending.
2. Create the completed archive only from a genuine finished task with model/runner evidence, guard records, matched sandbox item and receipt. Validate the entire chain; missing proof must not be backfilled with illustrative IDs.
3. Implement reset under the shared lock. Check unresolved attempts across all runs, defer unsafe reset, archive the old namespace, allocate fresh workflow IDs and reference the original completed archive. Preserve financial history, command/webhook dedup, allowance usage and evidence.
4. Make replay traverse the actual idempotent processing path. Show the existing attempt and prove the count of business attempts and provider payments stays unchanged; a read-only lookup alone is not replay evidence.
5. Deploy separate API, executor/worker, runner, fixture, frontend and durable PostgreSQL services. Add migration/release steps, least-privilege credentials, TLS/session configuration and restricted service connectivity.
6. Implement liveness/readiness, worker freshness, correlated redacted logs, bounded polling/backoff and actionable dependency failures. Document funding maintenance, restore/restart, unknown-payment investigation and evidence retention through the judge-access target.

**Primary files:** `backend/seed.py`, `routers/judge.py`, `routers/health.py`, `docker-compose.yml`, new Render configuration and operational runbooks.

**Exit gate:** EV15 passes for concurrent reset/dispatch, replay and preserved history. A clean checkout starts with documented configuration; hosted judge access works without personal provider keys; a restart retains evidence and financial state.

### M8 — Prove release readiness and prepare submission

**Owner:** lead coordinating frontend, AI and research responsibilities. **Dependencies:** M0–M7. **Target:** week 6; research begins in week 1.

1. Complete the requirement register: one row for each of 12 user stories, 38 functional requirements and 19 nonfunctional requirements, with owner, priority, test/evidence link and pass/pending status. Cover every EV01–EV16 case without treating local simulations as provider proof.
2. Run the financial concurrency/crash matrix against PostgreSQL, the three-family model evaluation, browser role/access flows and clean-checkout/hosted smoke checks. Repeat failed or changed cases and keep reproducible redacted reports.
3. Collect the specified thirty warm measurements and report acknowledgement, queue, runner, inference, provider-request and settlement timing separately. Report missed Should targets honestly.
4. Complete three actual agency-owner interviews and paired review observations. Record method, observations and limitations without invented customer statements or generalized savings claims.
5. Rehearse D01–D12 in 175 seconds, retaining the actual 320px contradiction, corrected run, genuine payout/item reconciliation, linked receipt and replay proof. Use truthful waiting or a clearly labeled genuine prior completed case when needed.
6. Finish `07-BACKEND_PLAN.md`, `08-UI_SPEC.md`, `09-TEST_PLAN.md` and `10-DEMO_AND_SUBMISSION.md` as implementation/runbook handoffs. Update README setup/status claims and verify MIT license, public repository/assets, tools list, hosted URL and the required public video under three minutes.
7. Confirm submission and judge-access dates against official requirements, assign an operations owner and prepare the submission pack. Publishing or submitting assets is a separate execution action, not accomplished by this plan.

**Exit gate:** all 67 Must requirements have passing evidence; NFR-07 results are reported; optional FR-38 status is explicit; no missing real-provider case is represented as complete. The final report records residual limitations and operational ownership.

## 5. Sequence, schedule and practical work allocation

The main dependency chain is M0 → M1 → M2 → M3 → M4 → M5 → M7 → M8. M6 starts once M1 and API contracts are stable, then joins M7. Provider/deployment spikes, fixture construction and research begin early; their final acceptance still depends on the gates above.

| Dates, 2026 | Main work | Required checkpoint |
| --- | --- | --- |
| 2–8 October | M0, start M1, recruit interview participants | Runnable baseline and actual provider/model/runner feasibility evidence |
| 9–15 October | M1/M2, fixture templates and frontend foundations | Durable commands, roles and approved real compilations for three families |
| 16–22 October | M3/M4, evidence and correction UI | Actual broken/corrected evidence, grounded contradiction and stale/uncertain holds |
| 23–29 October | M5, receipt/recovery UI | Guarded real payment plus reconciliation, replay, crash and cancellation evidence |
| 30 October–5 November | Complete M6/M7, finish research collection | Clean hosted judge journey with truthful seeds and safe reset |
| 6–12 November | M8, fix acceptance failures, rehearse and package | Complete evidence register and submission-ready assets |

Use backend/data, frontend, and AI/verification as responsibilities, not assumed dedicated staff. With one builder, execute the same dependency order and reassess calendar feasibility after M0. With multiple builders, frontend and fixture work can overlap backend work once contracts are fixed. Do not promise this schedule until weekly capacity is known.

Start with three reviewable changes: (1) repair startup/routing and isolate simulations; (2) establish PostgreSQL migrations plus database integrity tests; (3) implement sessions, command receipts and the durable worker. Then split each milestone into small changes whose acceptance evidence is reviewed with the implementation. Produce the first end-to-end responsive correction flow before extending its runner/reviewer proof to API and keyboard families; all three remain required for release.

If time slips, defer FR-38 and optional polish first, retain the fixed three-family scope, and report missed Should latency targets. Payment truth, grounded evidence, authority/role boundaries, durable idempotency, cancellation recovery and history retention are Must behavior and require an explicit scope revision to remove.

## 6. Verification and risk tracking

| Layer | Required evidence | Milestones |
| --- | --- | --- |
| Contract/build | Python syntax/import checks, frontend type/build checks, OpenAPI route/schema/error/auth coverage, reproducible dependency installation | M0–M8 |
| Database/commands | Real PostgreSQL migrations, grants, immutable-source constraints, concurrent commands, one-time ledger postings, lock/lease loss | M1/M2/M5/M7 |
| Runner/evidence | Actual browser/HTTP observations for six artifacts, decoded PNGs, stored/read-back hashes, isolation and tamper rejection | M3 |
| Actual model | Versioned canonical evaluation plus adversarial cases; genuine image inputs, citations, bounded calls, payment-spy counts | M2/M4 |
| Provider integration | Genuine item matching, signature verification, unclaimed recovery; separately labeled local timeout/failure/race simulations | M0/M5 |
| Product/operations | Role-specific browser flows, keyboard/focus checks, guarded reset/replay, clean deployment, retained evidence and research/performance reports | M6–M8 |

The highest risks are sandbox access/cancellation reproducibility, model grounding, drift between the schema sketches and executable SQL, and concurrency around payout dispatch. Bring each forward through M0 spikes and incremental PostgreSQL tests. Runtime and schema work are prerequisites; adding credentials to the current prototype is not an implementation milestone.

At each milestone, assess the project's five judging dimensions: technological implementation (actual observable execution), design (clear state and permitted actions), impact (real observations and limits), innovation (distinct compilation plus grounded contradiction), and presentation (an inspectable, truthful short demo). Record gaps alongside the acceptance report.

## 7. Assumptions

- “All” means the full documented MVP and its validation/deployment/submission preparation. This request creates a plan; application changes and external transactions are future work.
- The existing project context and PRD control scope. The referenced original pasted brief is not present in the inspected repository.
- Work begins from the current prototype, with useful structure retained and simulated runtime behavior replaced. No existing feature is credited as accepted without execution evidence.
- Budget caps apply to principal; observed fees are recorded separately. The allowance survives reset, and business attempts remain capped at the approved maximum of three.
- Provider choice, team capacity, funded sandbox accounts, hosted resources and operational ownership remain unconfirmed. Estimates and external schedule dates need validation before execution commitments.
- This root-level document matches the repository's current documentation layout. Existing references to a `docs/` directory should be reconciled in a later documentation pass.

## 8. Open questions

| Decision | Default or action while unresolved | Needed by |
| --- | --- | --- |
| Who is implementing, and how many hours per week are available? | Use responsibility-based ownership; revise the calendar after the first feasibility results. | M0 scheduling |
| Which structured-output/image model and credentials are available? | Keep the adapter neutral; evaluate actual access and schema/image support. | M0/M2 |
| Are a funded sandbox sender, two confirmed recipients and webhook configuration available? | Treat payout and cancellation feasibility as pending until observed. | M0 |
| Which PostgreSQL/Render configuration and encryption-key management will be used? | Choose one tested database version and separate service credentials/key custody. | M0/M1 |
| What workspace principal allowance and demo access policy should deployment use? | Require explicit configuration; preserve consumed allowance across resets. | M1/M5 |
| Can genuine unclaimed/cancellation evidence be produced within the two-recipient setup? | Investigate early and keep the Must gate pending until demonstrated. | M0 investigation; M5 acceptance |
| Who owns research, submission and access-through-judging operations? | Assign named owners and verify official dates before release. | M0 assignment; M8 confirmation |
