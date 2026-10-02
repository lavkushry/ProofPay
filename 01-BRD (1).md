# ProofPay — Business Requirements Document

Version: 0.1 | Date: 2 October 2026 | Phase: 1 | Status: implementation baseline; validation pending

## 1. Purpose and authority

> ProofPay compiles the review queue between 'work submitted' and 'payment released' into executable acceptance checks — and pays only when evidence passes.

This document defines the business problem, audience, outcomes, boundaries, and decisions for ProofPay's PayPal AI Hackathon MVP. It follows [00-PROJECT_CONTEXT.md](00-PROJECT_CONTEXT.md). The product behavior and acceptance criteria are expanded in [02-PRD.md](02-PRD.md). Foundational requirement IDs retain their meaning across documents.

This is a planned product. No customer interviews, review-time measurements, live application, model evaluations, or sandbox payment tests have been completed. Targets below are exit gates, not reported results. A documentation review cannot substitute for functional acceptance.

The lead is a backend/DevOps engineer. Capacity remains an assumption of 1–3 builders over six part-time weeks. The project must be submitted before 13 November 2026, 03:30 IST. The internal target is 12 November, 18:00 IST. Judge access remains available through 15 December, 16:00 UTC, with an operational target of 16 December, 00:00 UTC. [S01]

## 2. Business proposal

ProofPay serves small US software agencies that already pay freelance contractors through PayPal. The agency owner describes a bounded software change, reviews three AI-proposed executable checks, and authorizes conditional payment to a known contractor. Delivery produces trusted results and screenshots. The AI reviews those results against the claim, requests correction when evidence conflicts, and recommends release when the approved conditions pass. A backend executor checks authority and initiates the sandbox payout. The product then reconciles the recipient-level financial outcome and produces a linked receipt.

The business value hypothesis is less owner attention between delivery and payment, clearer correction requests, and a shared explanation of why a payment is held or completed. The MVP validates the workflow on a controlled fixture. It does not establish that arbitrary client software can be accepted safely or that agencies will buy the product.

PayPal performs the central financial action through Payouts. The AI performs two central judgment tasks: turning supported intent into checks and evaluating grounded evidence, including a claim/screenshot contradiction. Neither function is sufficient alone: passing a test does not confer payment authority, and an accepted payout request does not establish receipt by the contractor.

The concept can use other payment rails in a future product. The selected PayPal workflow is central to this submission; provider exclusivity is not a defensible differentiator.

## 3. Problem statement and current workflow

The problem hypothesis is a delivery review queue. An owner receives a message such as “mobile checkout is fixed,” reconstructs the original expectations, opens the delivery, tests the change, explains discrepancies, reviews a correction, and separately initiates payment. Evidence and payment state can sit in different tools. Delayed owner attention can delay both acceptance and the contractor's payment even when the work is adequate.

| Stage | Hypothesized friction | Evidence needed | Proposed change |
| --- | --- | --- | --- |
| Describe work | Completion conditions remain implicit or ambiguous | A redacted brief and owner's intended checks | Compile three supported checks before approval |
| Receive delivery | A claim does not prove behavior | Submitted claim, artifact version, and actual review steps | Bind trusted verification to the submitted version |
| Reject delivery | Corrections lack reproducible evidence | Example correction and contractor response | Share failed check, screenshot, and concise finding |
| Accept work | Owner repeats checks after each correction | Timed review sessions | Re-run the same approved checks on the new artifact |
| Pay contractor | Review outcome and financial initiation are disconnected | Payment initiation steps and wait times | Apply a previously approved conditional mandate |
| Confirm payment | Creation/processing may be mistaken for receipt | Actual transaction/item status handling | Reconcile the matched payout item before showing paid |

Measure active review time separately from calendar waiting time. For a measured period, review labor cost is the sum of active review minutes multiplied by the owner's stated hourly opportunity cost divided by 60. Payment delay is elapsed time from submitted delivery to reconciled item success; provider waiting and owner waiting must remain separate. Do not claim this entire delay is removable by ProofPay.

## 4. Target segment and validation boundary

### 4.1 Primary segment

Recruit US agency owners or technical leads who manage existing freelance software contractors, use PayPal, and personally review delivery. Recruit for actual recent review experience rather than enthusiasm for AI. The assumed workflow is small, fixed-price software maintenance work with an agreed amount and observable acceptance conditions.

The initial research sample is three agency owners. This sample can reveal workflow patterns and rejection reasons; it cannot estimate the market, prove statistical effectiveness, or support an industry-wide savings claim. Team size, transaction volume, and willingness to pay are research fields, not invented segmentation facts.

### 4.2 Product demonstration boundary

The MVP contains one agency workspace, one fixture application, two preconfigured contractor sandbox recipients, USD, exactly three acceptance checks per approved brief, and three brief families: responsive CSS, API endpoint repair, and keyboard accessibility. All business identities and deliveries in the public demo are simulated.

The fixture registry contains trusted broken/corrected versions. Contractors select those versions; they do not upload executable code. The compiler selects allowlisted test templates and parameters. General repository integration is outside the MVP. Describe measured fixture improvements as fixture results until a separate real-agency pilot supports broader claims.

### 4.3 Excluded audiences and needs

Consumer subscriptions, contractor discovery, general hiring, legal arbitration, arbitrary repository acceptance, multi-currency operations, live cross-border payouts, and escrow are outside this business baseline. A future commercial plan belongs in the Parking Lot until interviews show the workflow is valuable.

## 5. Stakeholder map and decision ownership

| Stakeholder | Need or responsibility | Authority | Success evidence |
| --- | --- | --- | --- |
| Agency owner | Define work and understand when payment can occur | Approve immutable mandates, supersede versions, resolve evidence ambiguity, request eligible cancellation | Approved snapshot; attributable resolution; clear receipt |
| Contractor | Understand checks, submit work, correct failures, inspect payment | Submit assigned allowlisted artifacts and view own records | Reproducible correction; same payment outcome as owner |
| Judge | Evaluate a complete working journey quickly | Assigned demo owner/contractor roles and guarded reset | No personal provider keys; broken/corrected/replay path works |
| Project lead | Deliver a coherent, safe sandbox implementation | Technical choices inside fixed stack and scope | Weekly exits, actual provider evidence, public run instructions |
| Teammates, if available | Build assigned frontend, AI, or validation work | Implementation responsibility; no additional financial authority | Reviews and artifacts matched to the same requirements |
| PayPal sandbox | Execute and report the financial transaction | Provider financial status | Matched item identifiers, amount, receiver binding, raw status |
| LLM service | Compile supported checks and review evidence | Recommendation through validated tools only | Grounded output, model/prompt version, uncertainty handling |
| Render and AG Grid | Host the working app and expose the review queue | Infrastructure and presentation capabilities | Accessible demo and inspectable queue/evidence details |

One person may fill multiple team responsibilities. Financial approvals still record the application actor and version. Project acceptance belongs to the owner; provider status belongs to PayPal. The model has neither approval nor money-moving authority.

## 6. Competitive position

The closest conceptual overlap is Paybond. “Evidence-based payment release” alone is not a strong novelty claim. The focused differentiator is a compiler for supported software acceptance checks coupled to an agency/contractor correction and PayPal reconciliation workflow.

| Product | Documented overlap | ProofPay's focused proposition | Claim that remains unproven |
| --- | --- | --- | --- |
| Upwork | Fixed-price milestones support work submission, review, change requests, and payment release. [S02] | Compile a software brief into executable checks for an existing agency/contractor relationship | Agencies prefer this focused review workflow; do not claim Upwork lacks support for existing relationships |
| Payman AI | Describes payment authorization, limits, approved payees, and audit controls for agents. [S03] | Couple conditional spend authority to attributable software delivery assessment and correction | This vertical workflow adds value beyond an agent payment-control layer |
| Paybond / Harbor | Describes agreement-bound evidence evaluation, release/refund/review decisions, and records. [S04] | Compile three different software brief families into trusted checks; demonstrate a concrete mobile contradiction and end-to-end contractor workflow | The compiler and agency experience are meaningfully distinct; do not claim proof-gated settlement is new |

The competitive test is observable: can an agency owner understand the approved checks, see exactly why the broken delivery fails, and follow the corrected delivery to a real sandbox item outcome? Feature-absence claims require separate competitor testing. No competitor has been trialed for this BRD.

## 7. Business goals and measurement contract

Goal IDs organize outcomes; they are not additional product requirements. Requirement references point to the binding acceptance criteria in section 9 and the PRD. All five judging criteria are equally weighted. No prize target justifies omitting a weak criterion. [S01]

| Goal | Business outcome | Judging criterion | Requirement references | Submission evidence |
| --- | --- | --- | --- | --- |
| G01 | Delegate bounded delivery-to-payment work without delegating unrestricted spend authority | Technological Implementation | FR-03–FR-04, FR-06–FR-07, FR-10–FR-14; NFR-01–NFR-05 | Actual runner, model, executor, and matched sandbox item records |
| G02 | Give owner and contractor a coherent explanation and next action | Design | US-01–US-03, FR-08–FR-09, FR-13, FR-15–FR-16 | Role walkthroughs, correction view, accessible status and receipt |
| G03 | Establish whether the review queue is a real, valuable problem for this segment | Potential Impact | NFR-09; US-01–US-02 | Three interviews, measured review sessions, limitations and findings |
| G04 | Demonstrate useful compilation and grounded contradiction detection | Innovation | FR-02, FR-05–FR-08 | Three materially different check sets; mobile claim/evidence conflict |
| G05 | Make the complete financial journey inspectable in 175 seconds and afterward | Presentation | US-03, FR-11, FR-13–FR-16, NFR-08 | Rehearsed public video; functioning workspace; replay resolving to one attempt |

### 7.1 Success metrics

| Metric | Definition and target | Collection method | Gate and interpretation |
| --- | --- | --- | --- |
| Agency problem validation | Three completed agency-owner interviews with recent review examples | Dated notes, consent, redacted workflow observations | Must collect, including negative findings; no market-wide inference |
| Review-time baseline | At least one manual and one assisted review observation per interviewed owner | Time active inspection, clarification, and decision separately; use comparable tasks and report order | Must measure; small descriptive sample, no significance claim |
| Review-time change | Median paired active-minute difference and percentage difference; exploratory target of 30% less active time | Report every pair, task conditions, median, and range; calculate percentages only with nonzero baseline | Aspirational target, not a release-safety gate; report failure honestly |
| Acceptance fidelity | All three canonical briefs yield three valid checks; all known broken/corrected cases produce the expected safe outcome | Compiler/runner/evidence evaluation report | Must pass before claiming the demonstrated workflow works |
| Unsafe release rate | Zero dispatched payouts when a required guard fails in the defined acceptance suite | Attempts and guard-decision records, including fault injection | Must pass; bounded-suite evidence is not universal safety proof |
| Replay safety | One successful payment and at most one unresolved attempt per obligation, including concurrent replay/restart cases | Application records plus provider item references | Must pass; count business attempts separately from transport retries |
| Financial truth | Zero paid labels derived only from creation acknowledgement or batch success | State/receipt assertions against actual matched item records | Must pass; unknown or stale status remains explicit |
| Contractor clarity | Each research participant can locate the failed check, reason, and correction action without explanation from the builder | Recorded observation and task result | Product acceptance observation; report confusion and adjust copy |
| Demo completeness | All D01–D12 beats visible in a video of 175 seconds | Rehearsal timing and evidence checklist | Must finish under three minutes with actual outputs |
| Judge operability | Hosted role walkthrough works without personal provider keys; access maintained through judging | Clean-session walkthrough and dated operational checks | Must meet submission access obligations |

Metric owners are responsibilities: the lead owns financial fidelity and operability; the PM/research responsibility owns interviews and timing; frontend responsibility owns clarity. A solo builder owns all three and records evidence separately from claims.

### 7.2 Research and decision protocol

Recruit the three owners during week 1. Ask about the last delivery they reviewed, who paid the contractor, how acceptance was established, time spent, causes of delay, existing automation, and reasons they would refuse automated release. Obtain consent before recording; use redacted examples and simulated recipient/payment data in prototype sessions.

For timing, define the start as opening a submitted delivery and the end as recording an acceptance or correction decision. Record active minutes, interruptions, calendar waiting, task family, and outcome. Compare matched supported tasks, vary manual/assisted order where feasible, and disclose learning effects. Provider processing time is excluded from active-review savings and reported separately.

Maintain a validation log with participant pseudonym, date, segment fit, observed problem, current workaround, timing rows, refusal conditions, and evidence references. Do not publish private client code or real financial records. A statement such as “two of three owners reported a review bottleneck” is usable only after those interviews actually occur.

If owners do not experience a meaningful bottleneck, revise the impact pitch and recruitment assumptions. Do not broaden the software/payment scope to rescue an unsupported claim. Any material product pivot first revises the project context.

## 8. Business operating rules

### 8.1 Authority and acceptance

The owner approves recipient, amount, USD currency, three checks, expiry, principal cap, maximum three business attempts, and conditional release authority. Approval records a protected receiver binding. Editing those fields creates a new mandate version; correcting a delivery does not. New versions retain the same obligation's payment history and cannot authorize a second completed payment.

All executable checks must pass. AI review must pass or have a grounded human resolution of ambiguity. A human cannot waive a failed executable check. A missing screenshot/result, mismatched artifact, uncertain model output, or invalid evidence reference holds release. Every hold exposes a reason and the permitted next action.

### 8.2 Budget and financial outcome

The adopted default is a principal-only cap. PayPal fees are recorded separately and sandbox funding includes fee headroom. Before dispatch, the app reserves principal atomically under the approved obligation. This is an internal control; it does not place money in escrow or guarantee the provider account has funds.

Creation acknowledgement starts processing. Only matched item status `SUCCESS` supports paid. Pending, on-hold, unknown, and unclaimed outcomes retain the reservation. Confirmed nonpayment may release it and, if the failure is eligible, allow a new numbered attempt within approved limits. Transport retries retain the same attempt and sender IDs. A cancellation request releases no budget until item reconciliation confirms return.

Expiry and supersession stop new initiation. Reconciliation of an already initiated transaction continues. Provider status and the contractor's claim cannot be erased by a judge reset.

### 8.3 Workflow and scope change ownership

The backend executor is the only component that calls PayPal, including OAuth and webhook verification. AI requests are recommendations. The executor independently checks evidence, mandate status, expiry, bound recipient, budget, attempts, and obligation history before dispatch.

Use the exact six-endpoint boundary from the project context. A fallback that adds Disputes APIs changes that boundary and requires a revised context and acceptance plan. It is not an implementation shortcut inside this MVP.

## 9. Business requirements baseline

These requirements reuse the context IDs. Must means needed for the MVP; Should is valuable but may miss its target with a documented result; Could is optional within scope; Won't is excluded. The PRD is the complete expanded requirement register and traceability matrix.

| ID | Priority | Business requirement | Given / When / Then acceptance criteria |
| --- | --- | --- | --- |
| FR-01 | Must | Preserve the bounded demonstration | Given a third recipient, unsupported artifact/family, or non-USD request, when submitted, then reject it explicitly and initiate no payment. |
| FR-02 | Must | Convert supported intent into checkable completion | Given each canonical supported brief, when compiled with ambiguity resolved, then produce exactly three valid checks and materially different check sets across families. |
| FR-03 | Must | Make authority reviewable and immutable | Given a valid approval, when recorded, then freeze its financial/check snapshot; later edits require a new version. |
| FR-04 | Must | Pay only under approved conditions | Given a payout recommendation, when any release guard fails, then hold dispatch and record the failed guard. |
| FR-06 | Must | Establish completion with trusted evidence | Given approved checks and a known artifact, when verified, then produce attributable structured results and applicable screenshots for that exact version. |
| FR-07 | Must | Detect the visible claim/evidence contradiction | Given the broken mobile delivery claiming a fix, when reviewed, then cite the claim, failed overflow result, and 320px screenshot and refuse release. |
| FR-08 | Must | Give the contractor an actionable recovery path | Given failed delivery, when the corrected artifact is submitted, then create a new run, retain the earlier findings, and keep the same approved mandate. |
| FR-10 | Must | Execute the central payment through PayPal | Given passing evidence and valid authority, when release is requested, then the executor creates the bound sandbox payout and records provider references. |
| FR-11 | Must | Report the contractor's actual financial state | Given payout creation or a verified event, when reconciled, then inspect the matched item; batch success alone never marks paid. |
| FR-12 | Must | Recover an eligible unclaimed payment truthfully | Given a confirmed unclaimed item, when cancellation is requested, then reconcile its actual outcome and release principal only on confirmed return. |
| FR-13 | Must | Preserve a shared payment explanation | Given a reconciled item, when permitted parties inspect the receipt, then brief, approval, delivery, evidence, decision, amount, fees, and provider references are linked. |
| FR-14 | Must | Avoid paying twice for repeated workflow events | Given replay or an unknown-outcome retry, when handled, then resolve to the existing attempt and reuse sender IDs. |
| FR-15 | Must | Deliver owner and contractor experiences | Given an assigned role, when a task is opened, then expose the permitted queue, approval/evidence surfaces, or submit/correction/status view. |
| FR-16 | Must | Keep judge exercises repeatable without rewriting money history | Given unresolved payment, when reset is requested, then defer it; when safe, create a new namespace and preserve financial/audit history. |
| NFR-01 | Must | Keep the demo sandbox-only and secrets controlled | Given a browser, model, runner, or fixture, when its data/configuration is inspected, then no PayPal secrets are present and live mode is rejected. |
| NFR-02 | Must | Retain payment uniqueness through failures and resets | Given concurrent workers, restart, or delayed replay, when processed, then each obligation has at most one unresolved attempt and one successful payment. |
| NFR-03 | Must | Keep principal accounting consistent with financial truth | Given a state transition, when accounted, then reserve, consume, or release principal once; pending/unclaimed outcomes retain it. |
| NFR-08 | Must | Preserve functional judge access | Given a judge visit through the access deadline, when supplied instructions are followed, then application roles, fixtures, evidence, and provider state are usable. |
| NFR-09 | Must | Support the impact pitch with observations | Given three completed interviews and measured review sessions, when findings are reported, then include actual results, negative findings, and limitations without fabricated savings. |

## 10. Day 1 payout and hosting go/no-go spike

The lead's location in India makes developer access an early dependency. PayPal's country table lists India for receiving and withdrawing, while its overview permits sandbox integration testing during live-access review. Neither statement proves that this developer account can run the proposed sender workflow. Test a US sandbox business sender; do not imply live Indian sending capability. [S05, S06]

| Step | Action within the approved boundary | Evidence to retain | Decision |
| --- | --- | --- | --- |
| 1 | Configure one US sandbox business sender and two contractor profiles in the Developer Dashboard; fund the sender for principal and fees | Redacted account references, environment, funding/setup checklist | Fail if required sandbox setup is unavailable |
| 2 | Use a backend-only executor spike to obtain OAuth and initiate a $1 USD payout to the first approved receiver | Correlation ID, persisted sender IDs, redacted request, creation response, batch ID | Creation acceptance alone is insufficient |
| 3 | Inspect batch and matched item through the two allowed GET operations | Item ID, bound amount/receiver match, raw item status, timestamps | Go criterion: actual matched item `SUCCESS` |
| 4 | Subscribe in the dashboard and receive a genuine transaction webhook; verify it using the allowed verification endpoint | Event ID, verification result, mapped item, redacted headers/payload | Financial events remain untrusted until verified |
| 5 | Repeat the same sender batch ID for the same spike attempt and inspect resulting provider references | Duplicate handling or reference to original batch; item count | No second obligation or fabricated dedup claim |
| 6 | Investigate an unclaimed scenario using one of the two configured recipient profiles; cancel only an eligible item and inspect return/fee behavior | Actual raw statuses, cancel response, item refresh, eligibility limitations | Unproven recovery stays a high risk; no third recipient or invented return |
| 7 | Deploy the trusted runner as a separate Render worker and verify fixture reachability and durable screenshot storage | Runner job/run ID, artifact digest, stored PNG/result, restart observation | No assumed nested Docker daemon or inbound worker service |

Complete the first spike on 2 October, with a written decision within 24 hours of starting. This timing is a planning target, not a completed milestone. Passing the core payout gate requires an actual successful item, usable server-held credentials, and a viable signature-verification path. The hosting gate requires runner access to the fixture and persistent evidence. Cancellation uncertainty can be tracked to the week 4 recovery gate but cannot be claimed implemented or tested meanwhile.

On failure, distinguish configuration, permissions, funding, temporary provider errors, and a structural inability to run the sandbox workflow. Perform a bounded diagnostic retry for a concrete correction; retain the same sender IDs for an uncertain attempt. Do not repeatedly initiate payments to test connectivity.

If payout access is structurally blocked, propose the documented Disputes-based fallback and stop payout-dependent implementation. That pivot needs a revised context, a new API boundary, a demonstrated sandbox dispute lifecycle, revised requirements, and a revised demo. No Disputes operation is authorized by the current six-endpoint MVP. If neither path is viable, do not present a simulated payment as working PayPal integration.

## 11. Risk register

Likelihood is a planning judgment, not a measured probability. Impact describes the consequence if the risk materializes. The lead owns each gate unless a teammate is explicitly assigned.

| Risk | Likelihood / impact | Early indicator | Mitigation and decision gate | Requirements / goal |
| --- | --- | --- | --- | --- |
| R01 — India-based developer cannot run the US sender sandbox flow | Unknown / critical | OAuth or payout access unavailable after correct setup | Day 1 actual $1 item-success spike; diagnose; revise context before Disputes pivot | FR-10–FR-11, NFR-01 / G01 |
| R02 — Review queue is not painful enough | Medium / high | Owners already automate checks or reject delegated release | Three interviews and paired observations; publish negative findings; narrow value claim | NFR-09 / G03 |
| R03 — Model proposes invalid checks or misreads evidence | Medium / critical | Unsupported template, invented baseline/ref, or pass against failed runner result | Allowlist/schema validation, trusted evidence, hard-fail dominance, uncertainty hold; evaluate all three families | FR-02, FR-06–FR-09 / G01, G04 |
| R04 — Replay or timeout causes duplicate payout | Medium / critical | Lost creation response, concurrent workers, stale event after reset | Persist attempt before dispatch, stable sender IDs, durable obligation uniqueness, retain unknown reservation | FR-14, NFR-02–NFR-03 / G01, G05 |
| R05 — UI overstates payment completion | Medium / critical | Paid shown after HTTP acceptance or batch-only result | Match recipient-level item and preserve raw status; explicit processing/unclaimed/unknown labels | FR-11, FR-13 / G01, G02 |
| R06 — Unclaimed cancellation or fee return differs from assumptions | Unknown / high | No reproducible unclaimed case or unclear cancellation response | Spike actual eligibility and return; reserve until confirmed outcome; keep fee ledger separate | FR-12, NFR-03 / G01 |
| R07 — Render runner cannot reach fixture or evidence is lost | Medium / high | Networking mismatch, worker restart drops PNGs | Separate Docker worker polling jobs; persist small evidence in PostgreSQL; prove restart/read-back early | FR-06, NFR-04, NFR-08 / G01, G05 |
| R08 — Scope exceeds part-time capacity | High / high | Core contradiction not working by week 3 | Cut arbitrary multi-brief generality and optional polish/sponsors; retain three fixed families and financial safety | FR-01–FR-02, FR-07, FR-11, FR-14 / G01, G04, G05 |
| R09 — Differentiation is too close to Paybond or a fixed CI trigger | High / high | Pitch relies only on evidence-gated release | Demonstrate three different compiled check sets and contractor correction/payment experience; acknowledge overlap | FR-02, FR-07–FR-08 / G04 |
| R10 — Shared demo leaks secrets or permits uncontrolled sandbox spend | Medium / high | Owner APIs lack role checks or reset clears financial history | Server-held keys, scoped sessions, funded sandbox limits, guarded reset, preserved obligation history | NFR-01–NFR-06, FR-16 / G01, G02 |
| R11 — Demo depends on provider/model timing | Medium / high | Rehearsal stalls or item remains processing | Truthful waiting states; genuine completed seed; visible elapsed-time cuts; never substitute fake success | FR-11, FR-16, NFR-07–NFR-08 / G05 |
| R12 — Hosted access fails during judging | Medium / high | Expired keys, exhausted wallet, lost evidence, sleeping services | Dated access/funding checks, operational ownership, reproducible Compose path; retain real historical receipts | NFR-08 / G02, G05 |

Critical unresolved financial risks block a claim of safe release. A demo may disclose an unproven recovery edge case, but Must requirements remain pending until checked; they cannot be silently downgraded to optional.

## 12. Delivery plan and investment discipline

| Period, 2026 | Business exit | Engineering dependency | Acceptance owner |
| --- | --- | --- | --- |
| 2–8 Oct | Interview recruitment, explicit payout/hosting go/no-go | Actual sandbox item success and runner evidence persistence | Lead + research responsibility |
| 9–15 Oct | Owner can define and approve supported work | Three-family compiler, immutable mandate, roles, obligation/budget model | Lead |
| 16–22 Oct | Broken delivery gives a credible correction; corrected delivery resolves it | Trusted evidence and grounded contradiction/uncertainty review | Lead + AI responsibility |
| 23–29 Oct | Conditional payment reaches a truthful recipient-level outcome | Executor, replay/restart protection, webhooks, cancellation recovery | Lead |
| 30 Oct–5 Nov | Owner, contractor, and judge have a complete product journey | AG Grid queue, portal, evidence/receipt views, genuine seeds, hosting | Frontend responsibility + lead |
| 6–12 Nov | Impact claims, functional demo, and submission are ready | Required acceptance evidence, 175-second recording, public licensed repo/video | Project owner |

The first investment decision is feasibility, not UI polish. Do not commit to a paid infrastructure tier, extra sponsor integration, or additional generalized repository support before the central workflow is working. Track actual model calls and hosting needs, then choose a budget from observed usage. No cost estimate is represented as a current vendor quote.

Potential future pricing is an interview topic: whether the owner values time saved, correction clarity, or reduced payment uncertainty. No subscription billing, transaction fee, or paid onboarding is part of the hackathon app. Business viability remains unproven until buyers use and value a real-work pilot beyond the fixture.

## 13. Sandbox, data, and submission boundaries

All transfers use funded PayPal sandbox accounts and simulated business data. Disable live endpoints/configuration. Internal budget reservations are neither escrow nor a guarantee. A mandate is application approval for a conditional sandbox operation; it is not represented as a legal contract or provider authorization product.

The MVP accesses no real agency repository, customer payment instrument, or contractor bank account. Research notes are consented and redacted; the public demo uses fictional people and fixture data. Keep PayPal/model credentials out of browser bundles, runner containers, model context, logs, screenshots, and the public repository. Publishing code does not require publishing service secrets.

Financial history, evidence, and webhook dedup records survive judge reset. Cancel only a verified eligible unclaimed item; continue reconciliation after expiry. Show actual principal and observed fees rather than promising a fee-inclusive cap.

The functional submission route is a hosted judge URL, backed by reproducible local setup. Publish the source/assets with a root MIT license, English description and accurate tools-used explanations, and a publicly visible YouTube demo under three minutes. Keep the working project available through judging. Listing APIMatic is permissible only if it is actually used; it is presently optional and excluded. [S01]

Prize strategy favors Agentic Commerce, PayPal + AI, Demo Delivery, AG Grid, and Render. The rules constrain prize combinations; targeting several awards does not imply they can all be won together. Product completeness across the equally weighted criteria takes precedence over prize-count framing. [S01]

## 14. Phase 1 red-team assessment

| Criterion | Skeptical question | Response built into this baseline | Evidence still required |
| --- | --- | --- | --- |
| Technological Implementation | Is AI attached to a predetermined payout? | Distinct compilation, attributable review, independent executor, item reconciliation and replay invariants | Actual compiler/runner/model/provider records and fault cases |
| Design | Can a contractor understand and recover from a hold? | Correction and receipt are shared product outcomes with specific next actions | Clean-session owner and contractor walkthroughs |
| Potential Impact | Where is evidence of a real agency problem? | Three-owner research and measured active-review time; no fabricated savings | Completed interviews and observations |
| Innovation | Is this Paybond with a new name? | Narrow software-check compiler and complete agency correction workflow; explicit competitive overlap | Three materially different check sets and comparison testing |
| Presentation | Will the audience see actual payment and duplicate protection? | 175-second arc with actual item success, linked receipt, and replay | Truthful rehearsal and public video |

The BRD passes a documentation consistency check against the five criteria. The product is not yet demonstrated. The weakest business assumption is demand; the earliest technical blocker is sandbox access.

## 15. Parking Lot

| Candidate | Why excluded now | Reconsideration trigger |
| --- | --- | --- |
| Arbitrary repositories or AI-generated executable tests | Breaks fixture and trusted-runner boundaries | Validated real-work pilot and revised isolation design |
| More agencies, recipients, currencies, or live sending | Exceeds scope and approval model | Revised project context and separate integration decision |
| Escrow, payment guarantees, or legal arbitration | Unsupported by the selected workflow | Separate product and legal/provider capability validation |
| Full contractor marketplace or hiring | Does not serve required demo beats | Evidence of demand beyond delivery review |
| Commercial subscription billing and pricing | Value/willingness to pay unvalidated | Agency interviews and a real-work pilot |
| APIMatic or extra sponsor integrations | No required workflow dependency yet | Concrete judged benefit without delaying core gates |
| Disputes fallback | Replaces the central payment workflow and API boundary | Failed access spike, documented pivot, revised context |

## 16. Sources and evidence status

Primary public sources were checked on 2 October 2026. They establish reported platform/product behavior, not ProofPay implementation or competitor feature absence. The context and supplied master brief establish the selected product constraints.

| Ref | Source | Use |
| --- | --- | --- |
| S01 | [Hackathon rules](https://paypalaihackathon.devpost.com/rules) and [overview](https://paypalaihackathon.devpost.com/) | Judging, submission, dates, access, prize constraints |
| S02 | [Upwork fixed-price review and payment](https://support.upwork.com/hc/en-us/articles/17974824831507--Review-and-pay-for-fixed-price-contracts-and-milestones) | Documented milestone review/change/payment overlap |
| S03 | [Payman agent authorization discussion](https://paymanai.com/events/ai-volution-trust-ai-money) | Documented agent payment-control overlap |
| S04 | [Paybond Harbor](https://paybond.ai/harbor) | Documented evidence evaluation and settlement overlap |
| S05 | [PayPal country capabilities](https://developer.paypal.com/payouts/supported-features/) | India access risk; no inference of live sending |
| S06 | [Payouts overview](https://developer.paypal.com/payouts/use-payouts/overview) | Sandbox testing and live-access distinction |
| S07 | [Payouts integration guide](https://developer.paypal.com/api/payouts/) and [API reference](https://developer.paypal.com/api/payments.payouts-batch/v1/) | Core financial operation and recipient-level reconciliation |
| S08 | [Render background workers](https://render.com/docs/background-workers) and [Docker](https://render.com/docs/docker) | Separate worker hosting assumption |

## 17. Assumptions

| ID | Assumption / default | Validation or consequence |
| --- | --- | --- |
| A-B01 | One to three builders have six part-time weeks | Confirm capacity; assign responsibilities rather than invent staffing |
| A-B02 | Small US agency owners personally experience review/payment friction | Three interviews with recent examples; revise impact claims if false |
| A-B03 | Existing contractors and observable software changes are a useful initial wedge | Interview refusal conditions and workflow fit |
| A-B04 | A US sandbox sender is available to the India-based developer | Day 1 actual payout gate; no implied live permission |
| A-B05 | A configured LLM supports structured tools and image input | Provider remains open; validate before provider integration |
| A-B06 | Principal-only cap, separate fees, maximum three business attempts | Existing default; fee-inclusive change requires a context revision |
| A-B07 | Three canonical families can be verified with trusted fixture templates | Compiler/runner evaluation; no arbitrary-repository claim |
| A-B08 | Unclaimed cancellation can be demonstrated within the two-recipient boundary | Spike; unresolved behavior remains explicit until checked |
| A-B09 | Render's separate runner worker can persist evidence | Hosting/network/restart spike; preserve Compose route |
| A-B10 | Research timing is descriptive and fixture-bound | Publish task/order/sample limitations; no generalized savings claim |

## 18. Open Questions

Existing defaults allow Phase 1 documentation to proceed. None of these is presented as an approval already received.

| ID | Question | Adopted default / deadline |
| --- | --- | --- |
| Q-B01 | Which LLM provider/model and API account will the implementation use? | Provider-neutral tools + vision adapter; decide before Phase 3 provider integration |
| Q-B02 | Should the budget cap principal only or principal plus fees? | Principal-only, fees separate; revise context before implementation if changed |
| Q-B03 | Are you solo or working with teammates, and what weekly capacity is available? | 1–3 part-time builders; keep responsibilities assignable and cut optional generality first |
