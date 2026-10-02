# ProofPay — Product Requirements Document

Version: 0.1 | Date: 2 October 2026 | Phase: 1 | Status: detailed implementation baseline; product acceptance pending

## 1. Product definition and document authority

> ProofPay compiles the review queue between 'work submitted' and 'payment released' into executable acceptance checks — and pays only when evidence passes.

ProofPay is a sandbox delivery-to-payment workflow for small US software agencies paying existing freelance contractors through PayPal. An owner approves bounded conditional authority. A trusted runner verifies a submitted artifact. AI reviews attributable evidence, requests correction, and recommends payment. A backend executor independently enforces the mandate, calls PayPal, and reconciles the recipient-level outcome.

Read [00-PROJECT_CONTEXT.md](00-PROJECT_CONTEXT.md) as the source of truth. [01-BRD.md](01-BRD.md) defines business goals G01–G05, research, risks, and the access spike. This PRD preserves US-01–US-03, FR-01–FR-16, and NFR-01–NFR-09, then adds requirements without renumbering them. Later system design, API, data, AI, backend, and UI documents must implement these contracts.

The project has documentation only. Statements using “shall,” “must,” or acceptance criteria describe required behavior, not completed implementation. No prototype tests, real sandbox payouts, interviews, model evaluations, or latency benchmarks have been run.

The fixed stack is React + TypeScript, shadcn/ui, AG Grid, FastAPI, PostgreSQL, a durable outbox worker, an isolated Docker Playwright runner, an LLM with structured tools and image input, Docker Compose, and Render. API contracts will use OpenAPI 3.1 YAML in Phase 2. Phase 3 creates actual backend/runner code; Phase 4 creates UI specifications and components. This document defines observable behavior rather than claiming those later artifacts already exist.

## 2. Product outcomes and success gates

| Outcome | Submission gate | Authority |
| --- | --- | --- |
| Bounded autonomous workflow | No payout when evidence, authority, budget, recipient, expiry, or obligation-history guards fail | FR-04, FR-10, FR-26; BRD G01 |
| Coherent experience | Owner and contractor can inspect the same correction reason and financial outcome | FR-08, FR-13, FR-15, FR-34; G02 |
| Credible impact | Three agency-owner interviews and measured manual/assisted review observations, with limitations | NFR-09; G03 |
| Useful AI | Three different supported briefs compile to materially different check sets; broken mobile claim is contradicted with cited evidence | FR-02, FR-07; G04 |
| Truthful demonstration | Actual item success, linked receipt, and duplicate resolution appear in the 175-second journey; judge access continues afterward | FR-11, FR-13–FR-16, NFR-08; G05 |

BRD measurement definitions apply. A proposed reduction in active review time is exploratory. It is not an established benefit, and it cannot relax a release-safety gate.

## 3. Scope and release boundary

### 3.1 Fixed MVP envelope

| Dimension | Included | Enforced exclusion |
| --- | --- | --- |
| Workspace | One agency with assigned owner, two contractor roles, and judge access | Additional agency creation or cross-workspace access |
| Software | One trusted fixture app with registry-controlled versions | Arbitrary repositories, archives, uploaded executable code, custom target URLs |
| Recipients | Two preconfigured sandbox recipient references | Third recipient, browser-supplied receiver overrides |
| Money | USD; principal-only cap; observed fees separate | Live mode, other currencies, escrow, fee-inclusive guarantee |
| Checks | Exactly three distinct executable checks per approved brief | Unsupported templates, missing/extra checks, AI-generated runner code |
| Intent families | Responsive CSS, API endpoint repair, keyboard accessibility | General software acceptance outside the three supported families |
| Payment obligation | One contractor amount per milestone across mandate versions | Split payments, partial releases, tips, or a second completed payout |
| Business attempts | Maximum three, including first initiation; only confirmed eligible nonpayment permits the next | Treating transport retries as fresh attempts or retrying unknown/unclaimed outcomes |

The $75 responsive-CSS case is the primary demo. The API and keyboard briefs remain mandatory compiler/runner evaluation cases and judge exercises. Research and tests use simulated identities and the same fixture; they do not expand the product to real repositories or live money.

### 3.2 MVP and stretch priorities

| Priority | Behavior | Requirement references | Reason |
| --- | --- | --- | --- |
| Must | All eight modules, broken/corrected path, grounded hold, real payout/item reconciliation, linked receipt, durable dedup | All Must FRs/USs/NFRs below | Core product and D01–D12 |
| Must | Three fixed brief families, uncertainty handling, expiry, unclaimed recovery, safe reset, genuine completed seed | FR-02, FR-09, FR-12, FR-16, FR-35, FR-37 | Technical credibility and judge operability |
| Should | Meet proposed warm acknowledgement and runner latency targets | NFR-07 | Design/Presentation; disclose actual results if missed |
| Could | Compare earlier and current delivery evidence side by side | FR-38 | Design/Presentation at D06–D08; removable without breaking correction |
| Won't for MVP | Arbitrary multi-brief generality, new rails/currencies/recipients, live payments, marketplace, extra sponsors | Parking Lot | Outside fixed scope or no demonstrated dependency |

MoSCoW is a release policy, not permission to falsify a pending feature. A Must implementation that has not passed acceptance remains pending. Cut arbitrary generality and the Could comparison first; preserve the three fixed evaluation families, contradiction moment, and item-reconciliation story.

## 4. Personas and access model

| Persona | Context and job | Core actions | Access boundary | Completion signal |
| --- | --- | --- | --- | --- |
| Agency owner | Reviews existing contractors' small software deliveries and controls approved spend | Compose brief, approve/supersede mandate, inspect evidence, resolve uncertainty, inspect retry/cancellation and receipts | Own agency only; cannot edit approved payload or waive failed tests | Clear accepted/corrected decision and truthful recipient-level outcome |
| Contractor | Needs reproducible feedback and payment visibility | View approved checks, submit known artifact and claim, read correction, resubmit, inspect own receipt | Assigned recipient/tasks only; no authority approval, budget mutation, or judge reset | Checks pass and actual payment state is understandable |
| Judge | Has minutes to assess implementation and presentation | Follow seeded broken/corrected journey, compare family outputs, replay, inspect history, request guarded reset | Assigned demo roles; no provider/model keys; app guards still apply | Actual evidence and transaction chain can be inspected independently |

Judge role switching must make the active role obvious. It uses application demo access, not PayPal account login. Changing the frontend role label cannot elevate backend permissions. An assigned owner role may approve only within the sandbox envelope and approved application controls.

## 5. Persona user stories

All stories are Must for the MVP. They describe user outcomes; the linked FRs and NFRs specify implementation obligations. Each story has an explicit Given/When/Then acceptance contract.

### 5.1 Agency owner

| ID | Priority | Story | Given / When / Then acceptance criteria | Key requirements |
| --- | --- | --- | --- | --- |
| US-01 | Must | As an owner, I want a bounded delivery-to-payment workflow so accepted work can be paid under my prior approval | Given a supported brief and recipient, when I approve three checks and conditional authority, then a passing delivery can request payment under the frozen mandate and expose its outcome. | FR-02–FR-04, FR-10–FR-13 |
| US-04 | Must | As an owner, I want ambiguity surfaced before I authorize payment | Given a brief missing a required supported parameter, when compilation identifies ambiguity, then I can supply clarification and no approval/payout is enabled until three valid checks are available. | FR-17–FR-18 |
| US-05 | Must | As an owner, I want approval to bind the terms I actually reviewed | Given draft terms and their version digest, when I approve or later revise them, then approval freezes that version and a revision creates a new one while retaining obligation payment history. | FR-03, FR-19–FR-20 |
| US-06 | Must | As an owner, I want to resolve unclear evidence without silently overriding a failure | Given all executable checks pass but AI is uncertain, when I record a cited resolution, then the original verdict remains visible; a failed executable check still prevents release. | FR-09, FR-25 |
| US-07 | Must | As an owner, I want a clear recovery action for a financial hold | Given failed, processing, or unclaimed payment, when I inspect it, then I see the reason, reserved principal, permitted action, and confirmed outcome without creating a duplicate attempt. | FR-11–FR-12, FR-26, FR-29–FR-32 |

### 5.2 Contractor

| ID | Priority | Story | Given / When / Then acceptance criteria | Key requirements |
| --- | --- | --- | --- | --- |
| US-02 | Must | As a contractor, I want evidence-based corrections so I can fix the right issue | Given failed artifact-bound evidence, when I open the correction and submit a corrected version, then verification resumes under the same approved criteria and preserves the previous findings. | FR-05–FR-08, FR-21–FR-23, FR-34 |
| US-08 | Must | As a contractor, I want to know the acceptance conditions before I submit | Given my assigned approved task, when I open the portal and select an allowed artifact, then I see its three checks, amount, authority deadline, claim field, and acknowledgement for that delivery. | FR-05, FR-15, FR-21, FR-34 |
| US-09 | Must | As a contractor, I want a trustworthy payment record | Given a payment attempt for my task, when I inspect status or receipt, then I see its actual state, amount, observed fees, last reconciliation time, and linked evidence while other contractors' data is denied. | FR-11, FR-13, FR-33–FR-34, NFR-06 |

### 5.3 Judge

| ID | Priority | Story | Given / When / Then acceptance criteria | Key requirements |
| --- | --- | --- | --- | --- |
| US-03 | Must | As a judge, I want to exercise the complete truthful sandbox journey | Given seeded owner/contractor access, when I follow broken delivery, correction, payment, and replay, then actual evidence, item state, receipt, and dedup behavior are inspectable without supplying keys. | FR-07–FR-08, FR-10–FR-16 |
| US-10 | Must | As a judge, I want to see the compiler handle different supported intent | Given the three canonical briefs, when I compile each, then each yields three distinct valid templates/parameters and the family check sets differ materially. | FR-02, FR-17–FR-18, NFR-17 |
| US-11 | Must | As a judge, I want visible proof that replay cannot pay twice | Given a completed or unresolved obligation, when I replay its delivery/event, then I receive the existing attempt reference and no new financial initiation is created. | FR-14, FR-27–FR-28, NFR-02 |
| US-12 | Must | As a judge, I want a fresh exercise without losing historical truth | Given the workspace's current financial state, when I request reset, then unresolved movement defers reset; a safe reset creates a fresh namespace and retains genuine completed/audit records. | FR-16, FR-35–FR-37, NFR-18 |

## 6. Canonical journey and edge behavior

### 6.1 Happy path with the required contradiction

| Beat | User action | Observable result | Required record |
| --- | --- | --- | --- |
| D01, 0–10s | Open agency Work Queue | Existing held/processing/paid examples have clear next actions | Task, workflow state, hold flags, last update |
| D02, 10–25s | Enter the responsive brief, known contractor, and $75 USD | Scope validation succeeds; draft is captured | Brief text/revision, recipient reference, proposed terms |
| D03, 25–42s | Compile checks | AI proposes overflow at 320px, unchanged cart total, and keyboard checkout reachability | Model/prompt/tool versions, three templates/parameters, ambiguity list |
| D04, 42–53s | Review and approve conditional authority | Frozen mandate appears with expiry, principal cap, and attempt limit | Approver, timestamp, version digest, protected receiver binding |
| D05, 53–72s | Contractor submits the broken version claiming the fix | Acknowledgement starts trusted verification; no payment yet | Claim, delivery ID, artifact digest, mandate digest, runner job |
| D06, 72–89s | Inspect evidence | Runner reports overflow; AI cites claim, failed check, and 320px screenshot; payment held and correction recorded | Immutable evidence bundle, per-check verdicts, contradiction references |
| D07, 89–109s | Contractor selects the corrected version and resubmits | New verification runs under the same approved mandate | New delivery/run IDs, predecessor link, preserved earlier findings |
| D08, 109–125s | Inspect passing evidence and release guards | All three executable checks and grounded review pass; executor reports guard outcome | Passing bundle, validated decision request, guard snapshot |
| D09, 125–143s | Observe automated initiation | Executor creates actual sandbox payout and shows returned batch ID | Persisted obligation/attempt/sender IDs, redacted provider response |
| D10, 143–161s | Open payment detail and receipt | Actual matched item success supports paid; receipt links the full chain | Item ID/status, principal, observed fees, reconciliation time |
| D11, 161–169s | Replay the delivery/event | Visible dedup feedback links the original attempt | Replay event, dedup outcome, unchanged payment count |
| D12, 169–175s | Switch owner/contractor views | Both show the same permitted financial outcome | Same task/receipt identity with role-scoped fields |

The AI initiates a recommendation after passing review; the prior owner approval supplies conditional authority. A second owner click is not required on the main happy path. A model/tool failure or uncertainty cannot be hidden by automatically changing that path to a fabricated successful decision.

Runner acceptance for the mobile case compares measured document width against the approved 320px viewport and records the actual values. The screenshot illustrates the same run. Do not invent a pixel measurement before execution. Cart totals come from a trusted manifest baseline; the compiler cannot fabricate expected values. Keyboard reachability comes from the trusted template and target reference.

### 6.2 Failure and recovery contract

| Condition | Product behavior and user action | Financial rule | Requirements |
| --- | --- | --- | --- |
| Unsupported or ambiguous brief | Explain unsupported intent or missing parameter; let owner clarify supported intent | No mandate approval or payout | FR-01–FR-02, FR-18 |
| Draft changes during approval | Reject stale approval digest and show current draft | No mixed-version authority | FR-19 |
| Broken result with an optimistic claim | Cite the disagreement and request correction | No dispatch while an executable check fails | FR-07–FR-08 |
| Missing/invalid/stale evidence reference | Show verification error or review hold; re-run against the correct artifact | No model-created evidence or release | FR-22–FR-24 |
| All tests pass, AI uncertain | Keep `verifying` with review flag; owner may resolve ambiguity with references | Failed tests cannot be waived; original verdict retained | FR-09, FR-25 |
| New delivery arrives before earlier review completes | Retain earlier run but mark it superseded for release; verify current delivery | Old decision cannot dispatch against a new current artifact | FR-21–FR-22 |
| Worker/model failure | Show stage and retry/review action; resume durable job or hold | No success fabricated and no new financial attempt for stage retries | FR-24, FR-27, NFR-10 |
| Mandate expires or is superseded before dispatch | Show failed authority guard; new version may be proposed | No initiation under old authority; payment history survives | FR-20, FR-26, FR-30 |
| Creation response is lost | Show outcome unknown/reconciling, inspect known identifiers, retransmit only the same attempt if appropriate | Retain reserve and sender IDs; no speculative new attempt | FR-14, FR-27, NFR-11 |
| Batch success but item unresolved | Show processing and last reconciliation time | Batch-only information never means paid | FR-11 |
| Confirmed eligible nonpayment | Show reason and remaining approved business attempts | New numbered attempt only if all guards still pass | FR-29 |
| Item unclaimed | Show unclaimed and eligible cancellation action | Retain reserve until return confirmed | FR-12, FR-31 |
| Recipient claims while cancellation is in flight | Reconcile actual item; show paid if matched success, cancelled only if return confirmed | Never infer return from the cancellation HTTP acknowledgement | FR-31 |
| Forged/duplicate webhook | Reject unverified state change; verified duplicate resolves to existing event/attempt | No duplicate dispatch or budget posting | FR-28 |
| Judge reset with unresolved movement | Defer reset and show the blocking attempt/reference | Do not erase financial history or imply funds were returned | FR-16, FR-37 |

## 7. Functional requirements by module

Each requirement below is defined once. Related context requirements are expanded, not replaced. In acceptance criteria, “no payout” means no new financial initiation; it does not cancel a provider transaction that already exists.

### 7.1 Briefs

The owner supplies a brief, supported family, assigned contractor reference, amount, principal cap, attempt limit, and expiry. The compiler sees the brief and authorized fixture manifest, not PayPal credentials or receiver addresses. Family selection is a scope constraint; AI still interprets the intent and binds the three templates and parameters. A family label alone is not a valid compilation result.

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-01 | Must | Enforce fixed scope at every entry point | Given unsupported family/fixture, third recipient, non-USD terms, or custom executable check, when submitted through any role/API, then reject with a specific reason and create no payment. |
| FR-02 | Must | Compile exactly three valid checks with meaningful family differences | Given the canonical responsive, API, and keyboard briefs and trusted manifest, when ambiguities are resolved and compilation runs, then each produces three distinct allowlisted checks with valid parameters; family sets differ materially and unsupported baselines are rejected. |
| FR-17 | Must | Capture and version supported brief input | Given authorized owner input, when saved, then retain text/revision, supported family, fixture reference, contractor reference, proposed financial terms, and actor; later edits create a new draft revision without rewriting approved history. |
| FR-18 | Must | Resolve ambiguity before approval | Given missing required intent/parameters or invalid compiler output, when compilation completes, then display ambiguities/questions or a failure reason, accept clarification, and keep approval disabled until exactly three valid checks exist. |

| Family | Canonical example | Required three template types | Trusted parameters |
| --- | --- | --- | --- |
| Responsive CSS | Fix horizontal overflow at 320px, preserve total, keep checkout keyboard reachable | `viewport_no_horizontal_overflow`; `cart_total_unchanged`; `keyboard_checkout_reachable` | Width 320; target/baseline/control references from manifest |
| API endpoint repair | Return a valid cart-total response with HTTP 200 and the expected total | `api_status`; `api_schema`; `api_total_matches_fixture` | Endpoint, HTTP status, schema and baseline references |
| Keyboard accessibility | Make checkout reachable and keyboard activatable with an accessible name | `keyboard_checkout_reachable`; `keyboard_activation`; `accessible_control_name` | Control reference, supported key action, trusted name expectation |

The compiler returns checks, ambiguities, and clarifying questions through `propose_checks`. Exact prompts/tool schemas follow in Phase 2. It does not return executable code or invent an unrestricted target URL.

### 7.2 Mandates

Approval freezes recipient reference and protected resolved receiver, amount, currency, checks, expiry, principal cap, maximum attempts, and conditional authority. Store decimal strings or cents for money. The initial example is $75 with a $75 principal cap and maximum three business attempts. Seed expiry is generated relative to setup rather than hardcoded to an already elapsed date.

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-03 | Must | Approve immutable mandate versions | Given a valid reviewed draft, when approved, then freeze its complete financial/check payload with approver, timestamp, digest and receiver binding; an attempted edit is rejected and must create a new version. |
| FR-04 | Must | Enforce conditional release authority | Given a decision request, when any release guard fails, then make no dispatch and persist a specific hold/guard result; only fully eligible current authority may initiate. |
| FR-19 | Must | Bind approval to the exact displayed draft | Given the owner's draft/version digest, when approval is submitted, then require exactly three distinct valid checks, positive USD amount within cap, allowed pinned receiver, future expiry and max attempts 1–3; a stale digest or invalid field blocks approval. |
| FR-20 | Must | Supersede without resetting the payment obligation | Given a revised draft for an existing milestone, when the new version is approved, then supersede prior initiation authority, preserve all snapshots/attempts/budget history, and require evidence bound to the new version before any permitted initiation; a prior successful payment cannot be paid again. |

Lifecycle status is an event-derived projection. Updating status does not edit the approval snapshot. A recipient-directory edit cannot change an approved protected receiver binding. A new version may change recipient before any payment only under all obligation/reservation guards; it cannot move or duplicate an unresolved provider transaction.

### 7.3 Deliveries

The contractor submits a selected allowlisted artifact and a completion claim. The backend resolves its immutable digest. Earlier claims and evidence remain inspectable. Submissions are permitted before financial initiation under the current task; once an attempt is unresolved or paid, the same obligation cannot be replaced with a new delivery to trigger another payout.

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-05 | Must | Bind delivery to a known artifact version | Given an allowlisted artifact selection, when submitted, then persist its digest, delivery ID, submitting actor and approved mandate digest, and bind all resulting verification evidence to them. |
| FR-08 | Must | Request correction and resume review | Given failed delivery findings, when `request_correction` is validated and a corrected artifact arrives, then persist an internal portal message with evidence references, create a new run, retain the predecessor, and preserve the approved criteria. |
| FR-21 | Must | Preserve delivery claims, order, and current selection | Given an assigned contractor submission before initiation, when accepted, then record claim text, artifact reference, delivery sequence and acknowledgement; repeated submission identity returns the existing delivery and invalid post-initiation replacement is rejected. |
| FR-22 | Must | Prevent stale verification from authorizing current delivery | Given a newer delivery or mandate version, when an older runner/model job finishes, then retain its history but mark it ineligible for release; only the latest selected delivery with matching current authority can proceed. |

### 7.4 Verification and AI review

The trusted runner executes approved templates in an isolated Playwright container. It produces structured results and applicable screenshots, bound to artifact and mandate digests. The model can inspect those artifacts and propose a verdict. It cannot execute code, choose arbitrary network targets, modify results, or manufacture evidence references.

`inspect_evidence` returns pass/fail/uncertain, per-check assessments, contradictions, concise rationale, and references. A runner failure dominates an optimistic model pass. Every per-check assessment cites existing evidence. Correction and payment recommendation tools operate only on validated task references; submitted claims are untrusted content, never tool instructions.

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-06 | Must | Execute approved checks and persist trusted evidence | Given three approved templates/parameters and a bound artifact, when the runner finishes, then persist a result for each check plus applicable screenshots, run ID, digests and timestamps; a timeout/error is not a pass. |
| FR-07 | Must | Ground review and detect the required contradiction | Given the broken responsive artifact claiming “fixed,” when reviewed, then fail release and cite the submitted claim, failed overflow result and same-run 320px screenshot; every per-check verdict has valid attributable references. |
| FR-09 | Must | Route uncertainty to human review | Given uncertain evidence review, when stored, then remain in `verifying` with `review_required=true` and no dispatch; only an authorized grounded resolution can clear ambiguity, and no failed executable check may be waived. |
| FR-23 | Must | Expose an attributable evidence manifest | Given an authorized evidence request, when opened, then show delivery/artifact/mandate/run identifiers, all three results and available screenshots; wrong-task, wrong-version or nonexistent references are rejected before model review. |
| FR-24 | Must | Validate structured AI tools and fail safely | Given malformed output, injection text, unsupported tools, invented references or a model timeout, when processed, then reject it, record the failure and apply a bounded repair/review policy; no failure can generate payment authority or invented successful evidence. |
| FR-25 | Must | Record a grounded human ambiguity resolution | Given all executable checks pass and AI remains uncertain, when an owner resolves it with rationale and valid references, then append the resolution and re-evaluate release guards while retaining the original verdict; resolution is denied for failed checks, stale evidence or another contractor's task. |
| FR-38 | Could | Compare previous and current delivery evidence | Given two retained deliveries for the same task, when comparison is opened, then show clearly labeled artifacts/run times and corresponding results without merging references or changing current release eligibility. |

The default AI failure policy permits at most two calls per compiler/reviewer stage, including one schema-repair attempt. A proposed 45-second timeout applies to each model call. Exhaustion becomes a compilation error or verification review hold, with no payout. Exact limits are implementation defaults to confirm in Phase 2; they are not measured performance.

A contractor-facing correction is an internal portal record. If model message generation fails, the UI may show the trusted check failures with an explicitly labeled system error; it must not fabricate an AI-authored rationale. The required recorded demo uses genuine model outputs.

### 7.5 Payments and reconciliation

All PayPal operations pass through the backend payment executor. The model's `request_payout(mandate_id, task_id, evidence_refs)` creates a decision request. It has no receiver/amount override, credentials, or unconditional dispatch capability.

| Allowed operation | Method and path | Product purpose |
| --- | --- | --- |
| OAuth | `POST /v1/oauth2/token` | Backend-only token acquisition/cache |
| Create payout | `POST /v1/payments/payouts` | Execute an eligible immutable obligation |
| Inspect batch | `GET /v1/payments/payouts/{batch_id}` | Discover/inspect batch items and aggregate state |
| Inspect item | `GET /v1/payments/payouts-item/{item_id}` | Establish matched recipient-level state |
| Verify event | `POST /v1/notifications/verify-webhook-signature` | Trust genuine sandbox events before reconciliation |
| Cancel unclaimed | `POST /v1/payments/payouts-item/{item_id}/cancel` | Request cancellation only while eligible |

No Orders, account-balance, invoice, refund, subscription, or Disputes API is added. Sender/recipient setup and webhook subscriptions happen in the Developer Dashboard. The configured PayPal base is `https://api-m.sandbox.paypal.com`. [S02–S04]

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-10 | Must | Initiate a bound payout through the executor alone | Given current passing evidence or permitted grounded resolution and valid authority, when the decision request is dispatched, then the executor binds receiver/USD amount from the frozen snapshot, calls only the sandbox payout endpoint and persists provider references. |
| FR-11 | Must | Reconcile the matched recipient item | Given creation, verified webhook or polling, when status is reconciled, then match batch/item/sender identity, receiver binding and amount, retain raw status, and mark paid only on matched item `SUCCESS`; batch success or a mismatch cannot mark paid. |
| FR-12 | Must | Cancel and reconcile eligible unclaimed payments | Given a confirmed `UNCLAIMED` item, when the owner or configured recovery policy requests cancellation, then refresh eligibility, call cancel through the executor, and retain reservation until item reconciliation proves return. |
| FR-14 | Must | Deduplicate workflow events and transport retries | Given the same delivery/decision/event or lost creation response, when processed again, then resolve the existing obligation/attempt, reuse its persisted sender IDs for permitted retransmission, and create no second financial initiation. |
| FR-26 | Must | Persist and display independent executor guard decisions | Given any payout recommendation, when evaluated, then record each guard's pass/fail and a user-facing reason; a failed guard exposes a permitted next action while blocking dispatch. |
| FR-27 | Must | Commit initiation identity and durable work atomically | Given eligible release, when accepted by the backend, then commit reservation, attempt identity, sender IDs and outbox work together before external dispatch; a crash/retry recovers that same attempt rather than minting another. |
| FR-28 | Must | Verify and deduplicate webhook processing | Given a PayPal event, when ingested, then verify genuine signature/context through the executor before financial mutation, store event ID/hash, and enqueue matched item reconciliation once; unverifiable/mismatched events change no payment state and cannot poison dedup for a later genuine event. |
| FR-29 | Must | Permit only eligible numbered business retries | Given provider-confirmed nonpayment, when retry is requested, then require a retryable reason, still-valid evidence/authority, remaining cap and fewer than approved attempts; create a new numbered attempt and sender IDs while retaining old item history. |
| FR-30 | Must | Continue reconciliation after authority ends | Given an existing initiated/unknown/unclaimed attempt, when its mandate expires or is superseded, then stop new initiation under that version and continue status/recovery handling without deleting the attempt or releasing reserve speculatively. |
| FR-31 | Must | Handle cancellation races and unknown outcomes truthfully | Given cancellation races with a claim or returns an ambiguous acknowledgement, when refreshed, then show the actual matched success/return/pending state, post budget changes once, and never label cancelled or release principal solely from HTTP acceptance. |
| FR-32 | Must | Show principal accounting separately from fees and wallet funding | Given mandate/attempt status, when payment detail is viewed, then display cap, reserved/consumed/released principal, remaining business attempts, observed fees and reconciliation time; configured allowance is not presented as a PayPal balance or escrow. |

### 7.5.1 Release guards

| Guard | Required condition | Failure behavior |
| --- | --- | --- |
| Environment and caller | Sandbox configuration and backend executor path | Configuration/authorization error; no provider call |
| Approval | Approved, current, non-exhausted immutable version; no supersession | Authority hold |
| Time | Executor time is strictly before approved expiry at dispatch | Expired hold; existing transaction still reconciles |
| Financial binding | Positive USD amount and pinned allowlisted receiver match snapshot | Binding error; no override from model/browser |
| Evidence identity | Current delivery, artifact digest, mandate digest, complete trusted bundle | Stale/missing evidence hold |
| Check completion | Exactly three approved checks completed and all executable outcomes pass | Correction or verification hold |
| Review | Grounded AI pass, or permitted cited resolution of uncertainty | Human-review hold; a failed test cannot be overridden |
| Obligation history | No previous successful payment and no other unresolved attempt across versions | Existing-attempt reference or exhausted hold |
| Attempts | New business attempt remains within approved maximum of three | Exhausted hold; transport retry does not increment count |
| Budget | Atomic principal reservation fits the applicable cap and configured workspace allowance | Budget hold; fees and actual wallet funding remain separate |
| Request identity | Sender IDs persisted and consistent with the existing attempt | Internal integrity hold; no regeneration after timeout |

The configured workspace principal allowance is a deployment control with a durable ledger across resets. Its numeric limit is an operational input, not a claim about PayPal funds. The approval screen also shows the mandate principal cap. Neither a model call nor a reset may increase these limits. The final data/transaction design will make their atomic relationship explicit.

### 7.5.2 Retry and status rules

The first financial initiation counts as business attempt 1. A transport retry, token refresh, duplicate webhook, worker redelivery, or replay of the same request does not consume another business attempt. An unresolved outcome cannot be replaced by a fresh attempt, even after mandate revision. Confirmed nonpayment is necessary but not sufficient for a new attempt: the failure must be eligible and all release guards must still pass.

Recheck current authority immediately before every payout-creation HTTP send, including retransmission of an uncertain attempt. If its mandate has expired or been superseded, preserve the unknown attempt and use eligible status reconciliation/provider investigation; do not retransmit a POST that could create payment after authority ended. Cancellation and status inspection of an existing item remain separate recovery operations.

PayPal's duplicate sender-batch protection is time-bounded. Durable app uniqueness persists beyond that window, but it cannot make a late retransmission safe by itself. Once an unresolved creation could be outside the provider's protection window, forbid automatic retransmission and require provider investigation; keep its reserve and history. [S05]

| Raw item status | Canonical app interpretation | Principal posting | User action |
| --- | --- | --- | --- |
| `SUCCESS` | PayoutItem `success`; task/receipt `paid` | Consume reservation once | Inspect linked receipt |
| `PENDING` | `processing` | Retain | Wait/reconcile |
| `ONHOLD` | `processing` with provider-hold/review flag | Retain | Inspect provider reason/reconcile |
| `UNCLAIMED` | `unclaimed` | Retain | Eligible cancellation/reconcile |
| `FAILED` | `failed` | Release only after nonpayment established | Inspect reason; eligible bounded retry |
| `BLOCKED` / `DENIED` | Item `blocked`; task `failed` with review flag | Establish outcome before release | Manual review; no automatic retry |
| `RETURNED` | `cancelled` with explicit return reason | Release returned principal once | Inspect returned outcome |
| Unknown status / external refund | Preserve raw data and reconciliation-review flag | No inferred posting or new payout eligibility | Investigation |

The webhook event name `PAYMENT.PAYOUTS-ITEM.SUCCEEDED` differs from raw item status `SUCCESS`. Batch notifications do not contain the required item details. Verify event authenticity and refresh the item through the allowed GET operations. Mock simulator events are test inputs, not proof of the main demo's financial outcome. [S03, S06]

Previously confirmed success remains an auditable historical fact. A late duplicate, stale provider response, or external-refund observation cannot reopen payment authority or silently erase that history. Preserve the new raw observation and route unexpected changes to review.

### 7.6 Receipts

A receipt is a readable chain of attributable records. While processing or unclaimed, label the surface as a payment record with the actual state. A completed-payment receipt requires matched success. Financial state is a projection over retained observations; its source records and approval payload remain unchanged.

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-13 | Must | Present a linked, role-scoped receipt | Given a reconciled item, when an authorized owner/contractor opens its record, then link brief, approved version, artifact, evidence, AI/human decision, executor guards, principal, observed fees and provider IDs; only matched success is labeled paid. |
| FR-33 | Must | Preserve provenance and explain incomplete payment records | Given missing fee information, pending status or a newer observation, when the receipt is viewed, then show unknown/not-yet-reported values explicitly, retain event timestamps and source references, and never replace missing data with invented zero fees or success. |

The receipt includes obligation/task identity, contractor display reference, mandate version/digest, delivery/run identifiers, three check outcomes, contradiction/resolution history where present, attempt number, batch/item/sender IDs, raw and canonical status, last reconciliation time, and principal/fee accounting. Provider identifiers are genuine returned values; examples or simulations are distinctly labeled outside executed records.

### 7.7 Contractor Portal and owner surfaces

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-15 | Must | Provide the specified coherent product surfaces | Given the active role and task, when navigating, then expose an AG Grid owner queue with sorting/status filtering and task detail, Brief Composer, Mandate Approval, Evidence Review, payment record/receipt, and permitted contractor submit/correction/status views; state and next action agree across surfaces. |
| FR-34 | Must | Scope the contractor portal and prevent authority mutation | Given an assigned contractor, when they view or submit a task, then show only their checks, delivery/correction and payment records; deny another recipient's data, approval, financial overrides, cancellation and reset even through direct API calls. |

| Surface | Minimum content and actions | State/error behavior | Requirements |
| --- | --- | --- | --- |
| Work Queue | Brief/task, contractor, amount, workflow status, hold reason, updated time; sort/filter; open detail | Empty queue explanation; loading indicator; fetch failure/retry; separate payment and verification states | FR-15, FR-26, FR-32 |
| Brief Composer | Supported family, brief, recipient, amount/cap/attempts/expiry, compiler preview/questions | Preserve draft on model/network error; unsupported intent explicit; approval disabled for ambiguity | FR-01–FR-02, FR-17–FR-18 |
| Mandate Approval | Three checks, bound contractor, principal/fees policy, authority/expiry, version/digest and prior-version diff | Stale draft conflict; clear approval consequences; immutable approved read view | FR-03–FR-04, FR-19–FR-20 |
| Evidence Review | Screenshot, three structured results, claim, AI rationale/references, prior deliveries | Run in progress; missing-evidence/error; contradiction hold; uncertain review action; no failed-check override | FR-06–FR-09, FR-23–FR-25 |
| Payment Record / Receipt | Linked timeline, guards, actual item state, IDs, principal/observed fees, reconciliation time | Processing/unclaimed/unknown explicit; conditional retry/cancel; incomplete data labeled | FR-10–FR-14, FR-26–FR-33 |
| Contractor Portal | Approved checks/amount/expiry, version selection, claim, corrections, resubmit and own receipt | Submission acknowledgement, verification progress, hold reason, rejected stale/post-initiation action | FR-05, FR-08, FR-21, FR-34 |
| Judge Workspace | Role launchers, exact demo steps, family examples, genuine completed case, replay and guarded reset | Readiness/dependency warnings from actual health; reset deferred when unresolved; no fake fallback success | FR-16, FR-35–FR-37 |

Every screen must explain what happened and what action is permitted. Status is not conveyed only by color. Detailed tokens, component trees, AG Grid configuration, and all screen empty/loading/error copy belong to Phase 4; these are its minimum acceptance obligations.

### 7.8 Judge Workspace, seeds, and reset

Seed one approved task awaiting the broken delivery and one genuinely completed case. A completed case is imported from actual runner/model/provider records produced by a prior sandbox execution; the seed script cannot construct a successful payout from invented IDs. Both use the same fixture and two allowed recipients.

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-16 | Must | Seed and reset safely for judges | Given a reset request, when unresolved initiated/unknown/unclaimed movement exists in the demo workspace, then defer with its reference; when safe, create a fresh demo namespace while retaining financial, dedup and audit history. |
| FR-35 | Must | Seed a mid-flow task and a genuine completed case | Given configured sandbox/model access and an actual completed execution bundle, when seeding, then create the approved mid-flow case and expose the real completed evidence/transaction chain; if no real completed bundle exists, report it missing and keep that case pending. |
| FR-36 | Must | Expose usable judge readiness and dependency failures | Given a judge visit, when readiness is checked, then show current application/database/worker/fixture dependencies and whether the actual completed seed exists; unavailable model/provider work stays failed/pending with instructions and cannot be shown as success. |
| FR-37 | Must | Preserve reset history and prevent budget restoration by reset | Given a safe reset, when committed, then assign fresh task/mandate/run identifiers and append a reset event, retain prior attempts/evidence/webhook dedup, and leave wallet funding and durable workspace allowance unchanged. |

Reset is serialized with initiation/worker selection so a payment cannot appear between the unresolved-state check and reset commit. Historical replay resolves against historical obligation keys even after a new run exists. A fresh demo run is a new exercise; it does not undo an earlier provider transaction or reopen the same obligation.

## 8. Nonfunctional and validation requirements

| ID | Priority | Requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| NFR-01 | Must | Enforce sandbox configuration and credential custody | Given browser/model/runner/fixture configuration or a live-mode request, when inspected, then those components contain no PayPal secrets and live base URLs are rejected; only the backend executor can perform the six PayPal operations. |
| NFR-02 | Must | Preserve durable obligation idempotency | Given concurrent workers, restart, transport uncertainty or replay after reset, when processed, then one obligation has at most one unresolved attempt and one successful payment; database uniqueness and locked transitions preserve this across mandate versions. |
| NFR-03 | Must | Keep principal reservations accurate and atomic | Given dispatch/status/cancellation transitions, when posted, then reserve/consume/release principal once under both mandate cap and durable workspace allowance; pending/unclaimed/unknown funds remain reserved, fees separate, and totals never become negative. |
| NFR-04 | Must | Isolate trusted execution | Given unapproved code/artifact/template/URL or a credential request, when a runner job is validated, then reject it; allowed runs use trusted fixture templates in a separate container without PayPal/model keys or financial write access. |
| NFR-05 | Must | Preserve attributable immutable history | Given approval, submission, review, supersession, payout, reconciliation or reset, when recorded, then append actor/service identity, timestamp, correlation ID, relevant digests and source references without rewriting prior approval/evidence/attempt records. |
| NFR-06 | Must | Enforce server-side role and workspace boundaries | Given another contractor's identifier or owner-only operation, when any API/evidence endpoint is called, then deny unauthorized access independent of UI role selection; responses disclose no protected cross-role evidence/financial bindings. |
| NFR-07 | Should | Meet proposed warm latency targets | Given 30 measured warm local runs, when benchmarked, then target p95 accepted-command acknowledgement <=1s and runner execution <=30s; report queue, model and provider waiting separately with hardware/environment and actual results. |
| NFR-08 | Must | Maintain functional judge access through judging | Given supplied access instructions before 15 December 2026, 16:00 UTC, when followed, then the working workspace, role access, fixtures, evidence and genuine provider records remain available; operational coverage targets 16 December, 00:00 UTC. |
| NFR-09 | Must | Validate impact through actual observations | Given three agency-owner interviews and at least one paired manual/assisted review observation per owner, when findings are reported, then include actual timings, task/order/sample limitations and negative results; no invented time-saving or customer claim appears. |
| NFR-10 | Must | Recover durable outbox work without loss | Given a crash before/after job claim, state commit or provider dispatch, when workers recover, then durable work resumes or remains visibly held, no accepted job vanishes, and redelivery preserves the same attempt and audit correlation. |
| NFR-11 | Must | Bound provider retry and unknown-outcome handling | Given token expiry, transient failure, lost response or delayed recovery, when handled, then use bounded backoff and the original attempt identity, retain unknown reservations, and prohibit unsafe late retransmission outside duplicate protection; secrets remain redacted. |
| NFR-12 | Must | Use exact USD arithmetic and unambiguous time | Given amounts, fees, expiry or timestamps, when validated/stored/compared, then use integer cents or exact decimals with two-place USD validation and UTC instants; invalid precision/currency and ambiguous expiry input are rejected rather than rounded silently. |
| NFR-13 | Must | Protect evidence integrity and bounded durable storage | Given runner PNG/JSON artifacts, when ingested or fetched, then verify digest/task/run/mandate binding, enforce allowed media and size limits, and persist bytes durably; tampered or mismatched data cannot authorize release. |
| NFR-14 | Must | Make the complete demo operable by keyboard | Given owner/contractor/judge navigation, when performed by keyboard, then controls and dialogs have names, focus behavior and visible state; failures/status are announced and never depend on color alone. |
| NFR-15 | Must | Expose operational health and attributable errors | Given application/job/payment failure, when observed, then structured logs and health/readiness expose stage, request/job/attempt correlation and actionable error without tokens, credentials or full receiver addresses. |
| NFR-16 | Must | Provide reproducible local and hosted execution | Given a clean checkout and documented environment inputs, when the final <=3 setup commands are followed, then Compose starts the required services and seeds truthful cases; hosted judges do not supply personal API keys. |
| NFR-17 | Must | Make AI evaluation bounded and reproducible | Given a compiler/reviewer call or canonical evaluation, when executed, then record model/prompt/schema versions, input/evidence hashes, valid output/error and call usage where reported; apply finite timeout/repair limits and all three family cases. |
| NFR-18 | Must | Retain evidence and financial history across resets | Given reset, restart or cleanup during judging, when performed, then preserve approved snapshots, actual evidence/decisions, attempts/provider references, webhook dedup and budget history through the access window; expired tasks cannot cause unsafe re-initiation. |
| NFR-19 | Must | Treat user/model content as untrusted at every boundary | Given malicious claim/brief, forged session/action or injected tool parameters, when processed, then enforce input/schema limits and server authorization, prevent forged money authority, and render untrusted text without executable markup. |

Default evidence limits for this controlled fixture are 512 KiB per PNG and 64 KiB per JSON result. These are initial implementation bounds, not tested output sizes. If a legitimate fixture artifact exceeds them, revise the bound explicitly before use; do not silently truncate payment evidence. All evidence remains in PostgreSQL for the MVP.

Command acknowledgement means the backend accepted durable asynchronous work. It does not mean compilation, verification or payout has finished. Show each waiting stage honestly. No fixed provider-settlement time is promised.

## 9. State, hold, and action contract

The context's canonical states apply. Hold/review reasons are flags, not invented PayPal statuses. Persist raw provider status separately. Phase 2 will expand every transition into system-level guards and recovery sequences.

### 9.1 Mandate lifecycle

| State | Meaning | Permitted transition / financial effect |
| --- | --- | --- |
| `draft` | Editable proposed terms | Owner approval to `approved` after full validation |
| `approved` | Immutable current authority | New initiation only while all guards pass; may become expired, superseded or exhausted |
| `expired` | Authority deadline reached | No new initiation under this version; existing payments continue reconciliation |
| `superseded` | Replacement version approved | No new initiation under old version; retain history and unresolved attempt |
| `exhausted` | Obligation settled or approved limits consumed | No further payment; success cannot be reopened by revision/reset |

When an unresolved attempt crosses expiry, the mandate projection may expire while the task remains reconciling. These are different facts, not inconsistent states.

### 9.2 Delivery and payment workflow

| Task state | Entry condition | Owner / contractor next action |
| --- | --- | --- |
| `brief_captured` | Valid supported draft captured | Compile/clarify and approve |
| `checks_approved` | Immutable mandate approved | Inspect approved terms; move to delivery waiting |
| `awaiting_delivery` | Approved task ready for submission | Contractor selects artifact and submits claim |
| `verifying` | Current delivery verification/review pending | Observe progress; owner resolves eligible uncertainty; no payment |
| `correction_requested` | Failed check or grounded contradiction | Contractor reads cited findings and resubmits |
| `evidence_passed` | Trusted checks pass and review/resolution valid | Executor evaluates guards; a guard hold remains visible |
| `payment_initiated` | Reserved attempt and durable dispatch work recorded | Inspect attempt; no replacement delivery/new initiation |
| `reconciling` | Provider creation/status work ongoing or outcome unknown | Wait, inspect status/failure; reservation retained |
| `paid` | Matched item `SUCCESS` | View genuine completed receipt; replay returns existing attempt |
| `failed` | Confirmed failure/block | Inspect reason; only eligible nonpayment permits bounded retry |
| `unclaimed` | Matched item `UNCLAIMED` | Eligible cancellation; inspect any concurrent claim |
| `cancelled` | Provider return confirmed | Inspect return record and one-time principal release |

`payment_initiated` means the application recorded a financial attempt, not that PayPal completed or even acknowledged it. PayoutItem `created` may lack an item ID until batch discovery. Do not show a fake identifier during that gap.

PayoutItem states are `created`, `processing`, `success`, `unclaimed`, `cancelled`, `failed`, and `blocked`. The context's `retry_within_budget` is obligation-level orchestration after a failed item; it creates a new attempt/item instead of mutating the old failed provider item back to created.

### 9.3 Required hold reasons

| Reason | State placement | Permitted resolution |
| --- | --- | --- |
| Ambiguous/unsupported brief | Draft/brief stage | Clarify supported intent; unsupported remains rejected |
| Failed check / claim contradiction | `correction_requested` | New corrected artifact and trusted run |
| Missing evidence / runner failure / AI output error | `verifying` | Bounded retry or attributable review; no pass fabrication |
| AI uncertainty | `verifying`, `review_required=true` | Grounded owner resolution only if every executable check passes |
| Stale artifact / superseded authority | Current stage with invalidation flag | Verify current artifact against current approved version |
| Expired authority / budget / exhausted attempts | `evidence_passed` or failed task with specific flag | Valid new authority where permitted; never reset obligation history |
| Unknown provider outcome / on-hold / unmatched item | `reconciling` with reason | Continue eligible reconciliation/investigation; retain reserve |
| Unclaimed | `unclaimed` | Cancel only if eligible; confirm actual outcome |
| Reset blocked | Workspace reset pending | Resolve all initiated unknown/unclaimed movement; retain history |

## 10. Requirement traceability

Criterion codes: T = Technological Implementation (BRD G01); D = Design (G02); I = Potential Impact (G03); N = Innovation (G04); P = Presentation (G05). Every requirement is mapped below. There are 12 user stories, 38 functional requirements, and 19 nonfunctional/validation requirements: 69 total. FR-38 is Could; NFR-07 is Should; the remaining 67 are Must.

Demo associations identify where a requirement supports the narrative. “Companion” means a judge/test path outside the 175-second main video; it does not claim all recovery scenarios fit in that recording. Proof artifacts below are required future evidence, not executed results.

### 10.1 User stories

| ReqID | Criteria | Demo association | Proof artifact |
| --- | --- | --- | --- |
| US-01 | T, D, I | D02–D10 | Owner approve-to-receipt walkthrough |
| US-02 | D, I | D06–D07 | Contractor correction/resubmission walkthrough |
| US-03 | T, D, P | D01–D12 | Clean-session judge journey |
| US-04 | T, D | D02–D03 companion | Ambiguity clarification and blocked approval |
| US-05 | T, D | D04 companion | Approval digest/version-conflict case |
| US-06 | T, D | D06–D08 companion | Cited ambiguity resolution and failed-check denial |
| US-07 | T, D | D08–D10 companion | Financial-state and recovery walkthrough |
| US-08 | D, I | D05, D07 | Assigned portal conditions/submission acknowledgement |
| US-09 | T, D | D10, D12 | Same receipt state; cross-contractor denial |
| US-10 | T, N | D03 companion | Three-family compiler evaluation |
| US-11 | T, P | D11 | Existing attempt reference and unchanged payment count |
| US-12 | T, D, P | D01, D11 companion | Safe/deferred reset and preserved history |

### 10.2 Functional requirements

| ReqID | Criteria | Demo association | Proof artifact |
| --- | --- | --- | --- |
| FR-01 | T, D | D02, D08 companion | Unsupported-scope rejection matrix |
| FR-02 | T, N | D03 | Three materially different valid check sets |
| FR-03 | T, D | D04 | Frozen snapshot and edit rejection |
| FR-04 | T | D06, D08 | Failed-guard dispatch denial |
| FR-05 | T | D05, D07 | Delivery/artifact/mandate digest chain |
| FR-06 | T, P | D05–D08 | Genuine runner results/screenshots |
| FR-07 | T, N, P | D06 | Claim/result/320px screenshot contradiction refs |
| FR-08 | D, I | D06–D07 | Internal correction and preserved predecessor |
| FR-09 | T, D | D06–D08 companion | Uncertainty hold and failed-check no-override |
| FR-10 | T | D08–D09 | Bound request and genuine sandbox response |
| FR-11 | T, P | D09–D10 | Matched item success; batch-only no-paid case |
| FR-12 | T | D10 companion | Eligible cancel and actual returned outcome |
| FR-13 | T, D, P | D10, D12 | Full linked receipt and role-scoped access |
| FR-14 | T, P | D11 | Replay/lost-response attempt identity |
| FR-15 | D, P | D01, D04, D06, D12 | AG Grid and complete screen walkthrough |
| FR-16 | T, D, P | D01, D11 companion | Reset defer/namespace/history case |
| FR-17 | T, D | D02 | Captured draft revision and actor |
| FR-18 | T, D, N | D03 companion | Clarification and invalid-output approval lock |
| FR-19 | T, D | D04 companion | Full validation and stale-digest rejection |
| FR-20 | T | D04, D08 companion | Supersession retaining obligation history |
| FR-21 | T, D | D05, D07 | Claim/sequence/idempotent submission records |
| FR-22 | T | D07–D08 companion | Older-job completion cannot dispatch |
| FR-23 | T, D, P | D06, D08 | Complete manifest and invalid-ref rejection |
| FR-24 | T | D03, D06 companion | Malformed/injected/timeout tool denial |
| FR-25 | T, D | D08 companion | Cited resolution with original verdict retained |
| FR-26 | T, D | D08 | Guard detail and permitted next action |
| FR-27 | T | D09, D11 companion | Atomic reservation/attempt/outbox crash recovery |
| FR-28 | T | D09–D10 companion | Genuine verified event; forged/duplicate handling |
| FR-29 | T | D08–D10 companion | Eligible numbered retry; unknown/blocked denial |
| FR-30 | T | D09–D10 companion | Reconciliation continues after expiry/supersession |
| FR-31 | T | D10 companion | Cancel/claim race and ambiguous response |
| FR-32 | T, D | D08–D10 | Principal/fees/allowance/attempts view |
| FR-33 | T, D, P | D10 | Unknown fee/status provenance labeling |
| FR-34 | T, D | D05, D07, D12 | Assigned portal and authority/access denial |
| FR-35 | T, D, P | D01, D10 companion | Genuine completed bundle and pending-if-missing |
| FR-36 | D, P | D01 companion | Actual readiness and dependency failure view |
| FR-37 | T, D, P | D01, D11 companion | Fresh namespace without history/budget restoration |
| FR-38 | D, P | D06–D08 optional | Labeled prior/current evidence comparison |

### 10.3 Nonfunctional and validation requirements

| ReqID | Criteria | Demo association | Proof artifact |
| --- | --- | --- | --- |
| NFR-01 | T | D08–D10 companion | Sandbox enforcement and secret-custody inspection |
| NFR-02 | T | D09, D11 companion | Concurrency/restart/reset idempotency matrix |
| NFR-03 | T | D08–D10 companion | Balanced one-time principal postings |
| NFR-04 | T | D05–D08 companion | Runner isolation and forbidden-input rejection |
| NFR-05 | T, D | D04, D06, D10–D11 | Append-only actor/digest/event chain |
| NFR-06 | T, D | D04, D12 companion | Direct API cross-role denial |
| NFR-07 | D, P | D03, D05–D10 | Thirty-run warm latency report |
| NFR-08 | D, P | D01–D12 | Clean-session access and operational checks |
| NFR-09 | I | D01 | Three interviews and paired review observations |
| NFR-10 | T | D05, D09, D11 companion | Worker crash and durable redelivery evidence |
| NFR-11 | T | D09–D10 companion | Lost response/token/backoff/late-retry hold |
| NFR-12 | T | D04, D08–D10 companion | Decimal/currency/expiry validation cases |
| NFR-13 | T | D05–D08 companion | Stored/read-back hashes and tamper denial |
| NFR-14 | D, P | D01–D12 companion | Keyboard/focus/status walkthrough |
| NFR-15 | T, P | D05–D10 companion | Redacted correlated logs and health output |
| NFR-16 | T, D, P | D01 companion | Clean-checkout Compose and hosted access |
| NFR-17 | T, N, P | D03, D06 companion | Versioned bounded three-family evaluation report |
| NFR-18 | T | D10–D11 companion | Reset/restart history and evidence preservation |
| NFR-19 | T | D02, D05–D09 companion | Injection, forged action and safe-rendering cases |

## 11. Release evidence and acceptance scenarios

This is the release-level evidence plan. Phase 5 expands it into executable/manual cases; Phase 3 adds appropriate backend/integration checks while implementing. None of these scenarios has been executed yet.

| Case | Setup / trigger | Required observed outcome | Requirement coverage |
| --- | --- | --- | --- |
| EV01 — compiler breadth | Compile all three canonical supported briefs, plus an ambiguous and unsupported brief | Three different valid sets of three; ambiguity holds; unsupported intent rejected | FR-01–FR-02, FR-17–FR-18, NFR-17 |
| EV02 — exact approval | Approve valid terms; attempt stale-digest, invalid amount/currency/expiry/receiver and approved-payload edits | Valid frozen snapshot; invalid/stale operations rejected; recipient-directory edit cannot redirect it | FR-03–FR-04, FR-19, NFR-01, NFR-12 |
| EV03 — contradiction and correction | Broken mobile claim, trusted 320px screenshot/result, corrected resubmission | Failure with cited contradiction; actionable internal correction; new run under same mandate passes | FR-05–FR-08, FR-21, FR-23 |
| EV04 — stale job | Delay old review, submit new delivery or approve new version, then finish old job | Old output retained but cannot dispatch; current bound evidence required | FR-20, FR-22, NFR-05 |
| EV05 — uncertain or invalid AI | Use all-pass tests with uncertain review, invented refs, injection and malformed output | Hold; permitted cited human resolution; no failed-test override; finite repair and no fabricated success | FR-09, FR-24–FR-25, NFR-17, NFR-19 |
| EV06 — actual PayPal payment | Run passing delivery with current authority and funded sender | Persisted attempt/outbox/reserve, genuine batch/item IDs and matched item success; linked receipt | FR-10–FR-11, FR-13, FR-26–FR-27, FR-32–FR-33 |
| EV07 — guard denial | Expired/superseded authority, cap exhausted, recipient mismatch, missing checks, prior success or unresolved attempt | Every failed guard records a reason; no new dispatch or reserve misuse | FR-04, FR-19–FR-20, FR-26, NFR-02–NFR-03 |
| EV08 — timeout and transport retry | Lose creation response or restart around dispatch | Existing attempt/sender IDs reused only while safe; unknown reserve retained; unsafe late retry held | FR-14, FR-27, NFR-10–NFR-11 |
| EV09 — business retry | Confirm retryable nonpayment; also try unknown, blocked and exhausted-attempt cases | Eligible numbered retry only under all guards; prohibited cases create no new attempt | FR-29, NFR-02–NFR-03 |
| EV10 — webhook trust | Genuine event, duplicate event, forged signature using a genuine event ID, and mismatched item | Genuine verified event reconciles; duplicate idempotent; forged/mismatched data cannot mutate state or block a later authentic event | FR-11, FR-28, NFR-05 |
| EV11 — unclaimed recovery | Actual eligible unclaimed item, cancellation, and claim race where reproducible | Actual return releases principal once; acknowledgement alone does not; concurrent success shown truthfully | FR-12, FR-31, NFR-03 |
| EV12 — authority ends after initiation | Expire or supersede a mandate with existing pending/unknown payment | New initiation denied; existing transaction still reconciles and remains visible | FR-20, FR-30, NFR-18 |
| EV13 — access and runner boundary | Direct cross-contractor requests, owner-only calls, custom target/code and tampered artifact | Server denial, isolated allowed runs, no financial/model secrets, invalid evidence blocked | FR-23–FR-24, FR-34, NFR-01, NFR-04, NFR-06, NFR-13, NFR-19 |
| EV14 — product/receipt walkthrough | Clean owner, contractor and judge sessions; keyboard navigation; missing fee/dependency cases | Complete screens, identical permitted state, explicit unknowns/errors, clear next actions and focus | FR-13, FR-15, FR-32–FR-36, NFR-14–NFR-15 |
| EV15 — seed/reset/replay | Seed without genuine completed bundle, then with one; reset concurrently with dispatch; replay old event | No invented complete case; unresolved reset deferred; safe reset fresh IDs and retained history/allowance; old replay dedup | FR-14, FR-16, FR-35–FR-37, NFR-02, NFR-18 |
| EV16 — operation and impact | Clean-checkout run, thirty warm measurements, hosted access checks, three interviews and paired observations | Actual reproducibility/performance/availability/research reports; limitations visible | NFR-07–NFR-09, NFR-16 |

Real provider scenarios and local fault simulations must be labeled separately. Local assertions can test handling of provider states but cannot prove an actual PayPal cancellation or settlement occurred. If a Must real-provider path remains unexercised, list it as pending in the release report.

## 12. Six-week build plan and weekly exit gates

The weeks match the source context. Work may overlap after dependencies are satisfied. A gate is passed by evidence, not by a completed document or a screen that displays sample success.

| Week / dates, 2026 | Build focus | Required exit evidence | Dependencies / ownership |
| --- | --- | --- | --- |
| 1 / 2–8 Oct | Day 1 US sandbox sender spike; genuine webhook/cancel investigation; Render runner reachability/storage; research recruitment | Actual $1 matched item success, redacted references, usable signature-verification path, stored/read-back screenshot; access/cancel uncertainties documented; interviews scheduled | Lead owns feasibility; research responsibility recruits; use BRD go/no-go |
| 2 / 9–15 Oct | Brief capture/clarification, three-family compiler, roles, immutable approval, recipient binding, obligation/principal ledger, outbox skeleton | EV01/EV02 core cases pass; three materially different sets; direct unauthorized approval denied; attempt/reserve commit model established | Feasible sender/runner; backend/data/AI responsibilities |
| 3 / 16–22 Oct | Trusted template runner, durable evidence, model review, mobile contradiction, correction loop, uncertainty policy | EV03 proves the exact 320px conflict and corrected pass under same mandate; EV04/EV05 prevent stale or uncertain dispatch | Immutable templates/mandates; lead + AI responsibility |
| 4 / 23–29 Oct | Executor, create/status mapping, verified webhooks, retries/recovery, item truth and unclaimed cancellation | EV06–EV12 financial gates; genuine item success; replay/restart cannot duplicate; actual cancellation evidence or explicit pending blocker | Trusted review and durable attempt model; lead owns financial acceptance |
| 5 / 30 Oct–5 Nov | AG Grid queue, complete owner/contractor surfaces, role permissions, linked receipt, judge landing, truthful seeds/reset, hosted integration | EV13–EV15 pass; clean judge journey without personal keys; genuine completed case and safe reset; keyboard/status checks | Financial/evidence chain usable; frontend + lead |
| 6 / 6–12 Nov | Full failure matrix, benchmark/research reporting, operational runbook, public licensed repository, 175-second video, submission | All Must requirements evidenced; Should result reported; clean checkout/hosted test; public YouTube <3min; complete tools list; access owner assigned | Team; submit by 12 Nov 18:00 IST, before 13 Nov 03:30 IST deadline |

### 12.1 De-scope order

Apply these cuts in order when schedule slips:

1. Remove arbitrary multi-brief generality, unsupported template exploration, and extra fixture/recipient/currency work. Keep the three fixed evaluation briefs and their distinct check sets.
2. Remove FR-38 side-by-side comparison and optional visual polish. Keep separate inspectable prior/current evidence, accessible status, and every required surface.
3. Remove optional sponsor integrations and elaborate navigation. Keep the AG Grid queue and actual Render deployment/reproducible Compose route.
4. Report missed Should latency targets with actual measurements; keep truthful asynchronous waiting and no fabricated shortcuts.

Never cut the 320px contradiction, corrected resubmission, independent mandate guards, actual payout/item reconciliation, linked receipt, durable replay safety, role/secret boundaries, or reset history. A fallback or removal of a Must feature is a scope revision, not an invisible de-scope.

## 13. Implementation handoff contracts

| Boundary | Required contract for the next phase | Forbidden shortcut | Requirement references |
| --- | --- | --- | --- |
| Frontend → FastAPI | Server-generated allowed actions, role-scoped records, version digests, durable acknowledgement and explicit stage/error | Deriving money authority or paid status in the browser | FR-15, FR-19, FR-26, NFR-06 |
| AI → backend tools | Validated fixture/evidence context and structured propose/inspect/correction/decision requests | Credentials, arbitrary executable code, amount/receiver overrides, invented references | FR-02, FR-07, FR-24, NFR-01 |
| Runner → evidence | Trusted template parameters, artifact/mandate/run binding, actual PNG/JSON bytes and digests | Screenshots uploaded by a claimant presented as trusted runner evidence | FR-05–FR-06, FR-23, NFR-04, NFR-13 |
| Outbox → executor | Durable obligation/attempt identity, reserved principal, independently rechecked guards | Fresh sender ID after an uncertain dispatch or unchecked model recommendation | FR-04, FR-14, FR-26–FR-27, NFR-02 |
| PayPal → reconciliation | Verified genuine events plus matched item inspection and retained raw status | Batch-only completion, cancel acknowledgement as returned funds, simulator as real success | FR-11–FR-12, FR-28, FR-31 |
| Reset/seed → history | Fresh exercise namespace, actual completed execution import, durable dedup/allowance/audit | Fabricated successful IDs or deletion of unresolved money history | FR-16, FR-35–FR-37, NFR-18 |

Phase 2 must deliver `03-SYSTEM_DESIGN.md`, `04-API_SPEC.yaml`, `05-DATA_MODEL.md`, and `06-AI_LAYER.md`. It must decide transaction/locking details, state-transition guards, full request/error schemas, constrained table/index design, runner privileges, exact prompts and the three-family evaluation harness. It must preserve these PRD IDs.

Phase 3 must deliver `07-BACKEND_PLAN.md` and actual FastAPI/SQLAlchemy/Alembic/outbox/PayPal/runner/Compose code, environment template, license, and truthful seed tooling. Phase 4 must deliver `08-UI_SPEC.md` and actual Work Queue, Evidence Review, and Receipt components. Phase 5 must deliver acceptance/test and demo/submission documents plus runbooks. A specification alone is not a working demo.

## 14. Phase 1 red-team review

| Criterion | Strongest challenge | Required product response | Current evidence status |
| --- | --- | --- | --- |
| Technological Implementation | The UI could be replaying a prewritten model/payment story | Three-family compiler, trusted evidence, tool validation, immutable guards, genuine provider item and crash/replay cases | Specified; not implemented/tested |
| Design | Too many states could leave either party unsure what happens next | Unified actual state, role-specific permitted action, cited correction, linked receipt, keyboard/empty/error behavior | Specified; walkthrough pending |
| Potential Impact | The fixture proves mechanics but not business value | Three real-owner interviews and measured paired review observations; disclose limits | Required; no research completed |
| Innovation | Fixed templates could look like CI, and Paybond already evaluates evidence | Intent-to-check parameter binding across three distinct families, image/claim contradiction, complete contractor recovery/payment workflow | Defined; eval and comparison pending |
| Presentation | Real provider waiting might break the 175-second arc | Genuine completed seed, honest processing, visible elapsed-time compression, actual success and replay reference | Required; recording/rehearsal pending |

The phase's documentary defense is complete: each challenge has requirements and a proof plan. No score or claim of winning is assigned before executed evidence exists.

## 15. Parking Lot

| Candidate | Exclusion reason | Re-entry condition |
| --- | --- | --- |
| Arbitrary repositories, generated runner code, uploaded archives | Breaks trusted-fixture scope | Revised isolation/threat model and validated real-work need |
| Additional brief families beyond the three fixed ones | Adds generality before core proof | Explicit context revision after MVP |
| More recipients/agencies/currencies or live mode | Expands financial/authorization scope | Separate product and provider integration decision |
| Escrow, guarantees, legal contracts or dispute adjudication | Unsupported by app reservations and six endpoints | Separate validated product/capability decision |
| Partial payments, bonuses, automated price negotiation | Breaks one approved amount per obligation | Revised business and mandate model |
| Full marketplace, consumer subscriptions, contractor ranking | Does not serve the required agency review journey | Demonstrated demand after the MVP |
| APIMatic and additional sponsors | Optional; no actual integration yet | Useful judged functionality without delaying gates |
| Disputes-based fallback | Changes central workflow and API boundary | Failed access gate followed by revised context/requirements/demo |

## 16. Sources and evidence policy

Official capabilities were checked on 2 October 2026 in the context/BRD research. External documentation is not proof that this app has run. Preserve actual execution evidence separately. Primary sources support platform facts; product limits and proposed targets are decisions from the owner/context and this PRD.

| Ref | Source | Purpose |
| --- | --- | --- |
| S01 | [Project context](00-PROJECT_CONTEXT.md) and [BRD](01-BRD.md) | Authority, audience, scope, metrics and phase gates |
| S02 | [PayPal Payouts guide](https://developer.paypal.com/api/payouts/) and [reference](https://developer.paypal.com/api/payments.payouts-batch/v1/) | Payout creation, batch and item operations |
| S03 | [Webhook verification](https://developer.paypal.com/api/rest/webhooks/rest/) | Genuine event authenticity boundary |
| S04 | [Unclaimed cancellation](https://developer.paypal.com/api/payments.payouts-batch/v1/payouts-item-cancel) | Eligibility and cancellation operation |
| S05 | [Duplicate sender-batch IDs](https://developer.paypal.com/docs/payouts/standard/integrate-api/customize/) | Time-bounded provider duplicate protection |
| S06 | [Payout webhook events](https://developer.paypal.com/payouts/webhooks/) and [processing statuses](https://developer.paypal.com/payouts/payment-processing/) | Item-level event/status interpretation |
| S07 | [Hackathon rules](https://paypalaihackathon.devpost.com/rules) | Functional access, public source/video, dates and judging |
| S08 | [Render workers](https://render.com/docs/background-workers) and [Docker](https://render.com/docs/docker) | Separate worker deployment assumption |

## 17. Assumptions

| ID | Assumption / default | Validation or effect |
| --- | --- | --- |
| A-P01 | Team remains 1–3 part-time builders with backend/DevOps lead | Confirm capacity and assign weekly ownership |
| A-P02 | Lead can configure a funded US sandbox sender and two recipients | Day 1 gate; no claim of live India sending |
| A-P03 | LLM supports structured tools and image input | Provider/model open; schema/vision spike before integration |
| A-P04 | Max attempts is at most three; principal-only cap, observed fees separate | Existing context default; fee policy change requires context revision |
| A-P05 | Fixture manifest and check templates are trusted and immutable by contractors/models | Runner registry and privilege tests |
| A-P06 | Same milestone has one durable obligation across mandate versions | Database/locking design must enforce at most one unresolved and one successful payment |
| A-P07 | An actual unclaimed/return case can be exercised within the two-recipient setup | Provider spike; label pending coverage until genuine evidence exists |
| A-P08 | Render worker can reach fixture and persist PNG/JSON in PostgreSQL | Network/storage/restart spike; no assumed nested Docker |
| A-P09 | Evidence limits of 512 KiB PNG and 64 KiB JSON fit the controlled app | Measure real artifacts; revise explicitly if needed |
| A-P10 | At most two model calls per stage with proposed 45s call timeout is practical | Phase 2 adapter/evaluation; failure remains safe hold |
| A-P11 | Warm acknowledgement/runner latency targets are achievable | Thirty-run report; targets remain unproven Should criteria |
| A-P12 | Deployment provides a finite workspace principal allowance retained across resets | Supplemental budget control; numeric limit is configuration, not wallet balance |
| A-P13 | Three owner observations can establish descriptive workflow evidence | Research limitations published; no generalized effectiveness claim |
| A-P14 | Genuine completed seed can be generated before recording/judging | If absent, readiness reports missing case; never manufacture provider IDs |

## 18. Open Questions

No open question blocks this product baseline. Unanswered decisions retain documented defaults; provider-specific integration and capacity commitments depend on their eventual answers.

| ID | Question | Adopted default / decision point |
| --- | --- | --- |
| Q-P01 | Which LLM provider/model and credentials will be available? | Provider-neutral structured tools + image adapter; select before Phase 3 integration |
| Q-P02 | Should `budget.max_total` include fees? | Principal-only with separate fees/headroom; a fee-inclusive cap needs a revised policy/context |
| Q-P03 | Solo or team, and how many hours per week are available? | 1–3 part-time builders; retain responsibilities and protect core gates while cutting optional generality |
