-- =====================================================================
-- ProofPay Database Schema
-- Authority: 05-DATA_MODEL.md & 03-SYSTEM_DESIGN.md
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Identity and Organizations
CREATE TABLE IF NOT EXISTS agencies (
  id uuid PRIMARY KEY,
  name text NOT NULL,
  advisory_lock_key bigint NOT NULL UNIQUE,
  principal_limit_cents bigint NOT NULL CHECK (principal_limit_cents > 0),
  reserved_cents bigint NOT NULL DEFAULT 0 CHECK (reserved_cents >= 0),
  consumed_cents bigint NOT NULL DEFAULT 0 CHECK (consumed_cents >= 0),
  current_demo_run_id uuid,
  CHECK (reserved_cents + consumed_cents <= principal_limit_cents)
);

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  role text NOT NULL CHECK (role IN ('owner','contractor','judge')),
  display_name text NOT NULL,
  UNIQUE (agency_id, id)
);

CREATE TABLE IF NOT EXISTS contractors (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  user_id uuid NOT NULL,
  recipient_ref text NOT NULL CHECK (recipient_ref IN ('contractor_maya','contractor_leo')),
  display_name text NOT NULL,
  current_binding_id uuid,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, recipient_ref),
  UNIQUE (agency_id, user_id),
  FOREIGN KEY (agency_id, user_id) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS recipient_bindings (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  contractor_id uuid NOT NULL,
  receiver_ciphertext bytea NOT NULL,
  receiver_hash text NOT NULL CHECK (receiver_hash ~ '^[0-9a-f]{64}$'),
  key_version text NOT NULL,
  confirmed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, contractor_id, id),
  FOREIGN KEY (agency_id, contractor_id) REFERENCES contractors(agency_id, id)
);

CREATE TABLE IF NOT EXISTS sessions (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  principal_user_id uuid NOT NULL,
  effective_user_id uuid NOT NULL,
  cookie_hash text NOT NULL UNIQUE,
  csrf_nonce text NOT NULL,
  is_judge boolean NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  FOREIGN KEY (agency_id, principal_user_id) REFERENCES users(agency_id, id),
  FOREIGN KEY (agency_id, effective_user_id) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS demo_runs (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  state text NOT NULL CHECK (state IN ('active','archived')),
  featured_archive_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id)
);

CREATE TABLE IF NOT EXISTS fixture_manifests (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  fixture_ref text NOT NULL CHECK (fixture_ref='checkout_fixture'),
  version integer NOT NULL CHECK (version > 0),
  digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest)='object'),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, fixture_ref, version)
);

CREATE TABLE IF NOT EXISTS artifact_versions (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  manifest_id uuid NOT NULL,
  artifact_ref text NOT NULL,
  family text NOT NULL CHECK (family IN ('responsive_css','api_endpoint','keyboard_accessibility')),
  digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  relative_path text NOT NULL,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, artifact_ref),
  FOREIGN KEY (agency_id, manifest_id) REFERENCES fixture_manifests(agency_id, id)
);

CREATE TABLE IF NOT EXISTS briefs (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  current_revision_id uuid,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, created_by) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS brief_revisions (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  brief_id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  title text NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
  body text NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
  family text NOT NULL CHECK (family IN ('responsive_css','api_endpoint','keyboard_accessibility')),
  manifest_id uuid NOT NULL,
  proposed_terms jsonb NOT NULL,
  digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, brief_id, id),
  UNIQUE (agency_id, brief_id, revision),
  FOREIGN KEY (agency_id, brief_id) REFERENCES briefs(agency_id, id),
  FOREIGN KEY (agency_id, manifest_id) REFERENCES fixture_manifests(agency_id, id)
);

CREATE TABLE IF NOT EXISTS delivery_tasks (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  demo_run_id uuid NOT NULL,
  brief_id uuid NOT NULL,
  state text NOT NULL CHECK (state IN ('brief_captured','checks_approved','awaiting_delivery',
    'verifying','correction_requested','evidence_passed','payment_initiated','reconciling',
    'paid','failed','unclaimed','cancelled')),
  current_delivery_id uuid,
  current_bundle_id uuid,
  review_required boolean NOT NULL DEFAULT false,
  hold_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, brief_id),
  FOREIGN KEY (agency_id, demo_run_id) REFERENCES demo_runs(agency_id, id),
  FOREIGN KEY (agency_id, brief_id) REFERENCES briefs(agency_id, id)
);

CREATE TABLE IF NOT EXISTS mandates (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  current_version_id uuid,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id),
  UNIQUE (agency_id, task_id, id),
  FOREIGN KEY (agency_id, task_id) REFERENCES delivery_tasks(agency_id, id)
);

CREATE TABLE IF NOT EXISTS outbox_events (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  task_id uuid,
  event_type text NOT NULL,
  dedup_key text NOT NULL,
  payload jsonb NOT NULL,
  stage_state jsonb NOT NULL DEFAULT '{}'::jsonb,
  state text NOT NULL CHECK (state IN ('ready','leased','done','failed','held')),
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_token uuid,
  lease_until timestamptz,
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  last_error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, dedup_key),
  FOREIGN KEY (agency_id, task_id) REFERENCES delivery_tasks(agency_id, id)
);

CREATE TABLE IF NOT EXISTS ai_interactions (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  job_id uuid NOT NULL,
  stage text NOT NULL CHECK (stage IN ('compiler','reviewer')),
  brief_revision_id uuid,
  bundle_id uuid,
  model_ref text NOT NULL,
  prompt_version text NOT NULL,
  schema_version text NOT NULL,
  input_digest text NOT NULL,
  input_refs jsonb NOT NULL,
  output jsonb,
  output_digest text,
  validated boolean NOT NULL,
  error_code text,
  usage jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, job_id) REFERENCES outbox_events(agency_id, id),
  FOREIGN KEY (agency_id, brief_revision_id) REFERENCES brief_revisions(agency_id, id)
);

CREATE TABLE IF NOT EXISTS compilations (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  brief_revision_id uuid NOT NULL,
  job_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('queued','running','ready','ambiguous','failed','stale')),
  interaction_id uuid,
  proposal jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, brief_revision_id) REFERENCES brief_revisions(agency_id, id),
  FOREIGN KEY (agency_id, job_id) REFERENCES outbox_events(agency_id, id),
  FOREIGN KEY (agency_id, interaction_id) REFERENCES ai_interactions(agency_id, id)
);

CREATE TABLE IF NOT EXISTS mandate_versions (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  mandate_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  brief_revision_id uuid NOT NULL,
  compilation_id uuid NOT NULL,
  contractor_id uuid NOT NULL,
  recipient_binding_id uuid NOT NULL,
  lifecycle_state text NOT NULL CHECK (lifecycle_state IN ('draft','approved','expired','superseded','exhausted')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  principal_cap_cents bigint NOT NULL CHECK (principal_cap_cents >= amount_cents),
  currency text NOT NULL CHECK (currency='USD'),
  max_attempts smallint NOT NULL CHECK (max_attempts BETWEEN 1 AND 3),
  expires_at timestamptz NOT NULL,
  public_payload jsonb NOT NULL,
  payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
  approved_by uuid,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id, id),
  UNIQUE (agency_id, mandate_id, id),
  UNIQUE (agency_id, mandate_id, version),
  FOREIGN KEY (agency_id, task_id, mandate_id) REFERENCES mandates(agency_id, task_id, id),
  FOREIGN KEY (agency_id, brief_revision_id) REFERENCES brief_revisions(agency_id, id),
  FOREIGN KEY (agency_id, compilation_id) REFERENCES compilations(agency_id, id),
  FOREIGN KEY (agency_id, contractor_id, recipient_binding_id) REFERENCES recipient_bindings(agency_id, contractor_id, id),
  FOREIGN KEY (agency_id, approved_by) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS acceptance_checks (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  mandate_version_id uuid NOT NULL,
  check_id text NOT NULL CHECK (check_id IN ('C01','C02','C03')),
  template_type text NOT NULL CHECK (template_type IN ('viewport_no_horizontal_overflow',
    'cart_total_unchanged','keyboard_checkout_reachable','api_status','api_schema',
    'api_total_matches_fixture','keyboard_activation','accessible_control_name')),
  params jsonb NOT NULL CHECK (jsonb_typeof(params)='object'),
  compiled_by text NOT NULL CHECK (compiled_by='ai'),
  approved boolean NOT NULL DEFAULT false,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, mandate_version_id, id),
  UNIQUE (agency_id, mandate_version_id, check_id),
  UNIQUE (agency_id, mandate_version_id, template_type),
  FOREIGN KEY (agency_id, mandate_version_id) REFERENCES mandate_versions(agency_id, id)
);

CREATE TABLE IF NOT EXISTS deliveries (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  mandate_version_id uuid NOT NULL,
  artifact_version_id uuid NOT NULL,
  artifact_digest text NOT NULL,
  mandate_digest text NOT NULL,
  submitted_by uuid NOT NULL,
  claim text NOT NULL CHECK (length(claim) BETWEEN 1 AND 4000),
  claim_digest text NOT NULL,
  sequence integer NOT NULL CHECK (sequence > 0),
  previous_delivery_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id, id),
  UNIQUE (agency_id, task_id, mandate_version_id, id),
  UNIQUE (agency_id, task_id, sequence),
  FOREIGN KEY (agency_id, task_id, mandate_version_id) REFERENCES mandate_versions(agency_id, task_id, id),
  FOREIGN KEY (agency_id, artifact_version_id) REFERENCES artifact_versions(agency_id, id),
  FOREIGN KEY (agency_id, submitted_by) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS verification_jobs (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  delivery_id uuid NOT NULL,
  state text NOT NULL CHECK (state IN ('queued','running','completed','error','stale')),
  inputs jsonb NOT NULL,
  input_digest text NOT NULL,
  worker_id text,
  lease_token uuid,
  lease_until timestamptz,
  lease_attempt integer NOT NULL DEFAULT 0,
  started_at timestamptz,
  completed_at timestamptz,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id, id),
  UNIQUE (agency_id, task_id, delivery_id, id),
  FOREIGN KEY (agency_id, task_id, delivery_id) REFERENCES deliveries(agency_id, task_id, id)
);

CREATE TABLE IF NOT EXISTS evidence_bundles (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  delivery_id uuid NOT NULL,
  mandate_version_id uuid NOT NULL,
  verification_job_id uuid NOT NULL,
  artifact_digest text NOT NULL,
  mandate_digest text NOT NULL,
  bundle_digest text NOT NULL,
  manifest_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id, id),
  UNIQUE (agency_id, mandate_version_id, id),
  UNIQUE (agency_id, verification_job_id),
  UNIQUE (agency_id, task_id, mandate_version_id, id),
  FOREIGN KEY (agency_id, task_id, mandate_version_id, delivery_id)
    REFERENCES deliveries(agency_id, task_id, mandate_version_id, id),
  FOREIGN KEY (agency_id, task_id, delivery_id, verification_job_id)
    REFERENCES verification_jobs(agency_id, task_id, delivery_id, id),
  FOREIGN KEY (agency_id, manifest_id) REFERENCES fixture_manifests(agency_id, id)
);

CREATE TABLE IF NOT EXISTS evidence_results (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  bundle_id uuid NOT NULL,
  mandate_version_id uuid NOT NULL,
  acceptance_check_id uuid NOT NULL,
  outcome text NOT NULL CHECK (outcome IN ('pass','fail','error')),
  observations jsonb NOT NULL,
  result_digest text NOT NULL,
  completed_at timestamptz NOT NULL,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, bundle_id, acceptance_check_id),
  FOREIGN KEY (agency_id, mandate_version_id, bundle_id) REFERENCES evidence_bundles(agency_id, mandate_version_id, id),
  FOREIGN KEY (agency_id, mandate_version_id, acceptance_check_id) REFERENCES acceptance_checks(agency_id, mandate_version_id, id)
);

CREATE TABLE IF NOT EXISTS evidence_artifacts (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  bundle_id uuid NOT NULL,
  check_id text CHECK (check_id IN ('C01','C02','C03')),
  media_type text NOT NULL CHECK (media_type IN ('image/png','application/json')),
  digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  content bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, bundle_id) REFERENCES evidence_bundles(agency_id, id)
);

CREATE TABLE IF NOT EXISTS corrections (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  delivery_id uuid NOT NULL,
  bundle_id uuid NOT NULL,
  review_interaction_id uuid NOT NULL,
  contractor_message text NOT NULL CHECK (length(contractor_message) BETWEEN 1 AND 2000),
  evidence_refs jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, task_id, delivery_id) REFERENCES deliveries(agency_id, task_id, id),
  FOREIGN KEY (agency_id, task_id, bundle_id) REFERENCES evidence_bundles(agency_id, task_id, id),
  FOREIGN KEY (agency_id, review_interaction_id) REFERENCES ai_interactions(agency_id, id)
);

CREATE TABLE IF NOT EXISTS review_resolutions (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  bundle_id uuid NOT NULL,
  review_interaction_id uuid NOT NULL,
  resolved_by uuid NOT NULL,
  rationale text NOT NULL CHECK (length(rationale) BETWEEN 1 AND 1000),
  evidence_refs jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, task_id, bundle_id) REFERENCES evidence_bundles(agency_id, task_id, id),
  FOREIGN KEY (agency_id, review_interaction_id) REFERENCES ai_interactions(agency_id, id),
  FOREIGN KEY (agency_id, resolved_by) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS decision_requests (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  mandate_version_id uuid NOT NULL,
  bundle_id uuid NOT NULL,
  source text NOT NULL CHECK (source IN ('ai','owner_resolution','owner_reevaluation')),
  review_interaction_id uuid NOT NULL,
  state text NOT NULL CHECK (state IN ('queued','held','deduplicated')),
  evaluation_generation integer NOT NULL DEFAULT 1,
  request_digest text NOT NULL,
  evidence_refs jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id, id),
  UNIQUE (agency_id, task_id, mandate_version_id, id),
  FOREIGN KEY (agency_id, task_id, mandate_version_id) REFERENCES mandate_versions(agency_id, task_id, id),
  FOREIGN KEY (agency_id, task_id, mandate_version_id, bundle_id)
    REFERENCES evidence_bundles(agency_id, task_id, mandate_version_id, id),
  FOREIGN KEY (agency_id, review_interaction_id) REFERENCES ai_interactions(agency_id, id)
);

CREATE TABLE IF NOT EXISTS payment_obligations (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  currency text NOT NULL CHECK (currency='USD'),
  next_attempt_no smallint NOT NULL DEFAULT 1 CHECK (next_attempt_no BETWEEN 1 AND 4),
  success_attempt_id uuid,
  reserved_cents bigint NOT NULL DEFAULT 0 CHECK (reserved_cents >= 0),
  consumed_cents bigint NOT NULL DEFAULT 0 CHECK (consumed_cents >= 0),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, task_id),
  UNIQUE (agency_id, task_id, id),
  FOREIGN KEY (agency_id, task_id) REFERENCES delivery_tasks(agency_id, id)
);

CREATE TABLE IF NOT EXISTS payment_attempts (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  task_id uuid NOT NULL,
  obligation_id uuid NOT NULL,
  mandate_version_id uuid NOT NULL,
  decision_request_id uuid NOT NULL,
  attempt_no smallint NOT NULL CHECK (attempt_no BETWEEN 1 AND 3),
  principal_cents bigint NOT NULL CHECK (principal_cents > 0),
  currency text NOT NULL CHECK (currency='USD'),
  sender_batch_id varchar(256) NOT NULL UNIQUE,
  sender_item_id varchar(63) NOT NULL UNIQUE,
  request_ciphertext bytea NOT NULL,
  request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN ('prepared','dispatching','unknown','processing',
    'unclaimed','success','failed','cancelled','blocked')),
  unresolved boolean NOT NULL DEFAULT true,
  nonpayment_confirmed boolean NOT NULL DEFAULT false,
  successful boolean NOT NULL DEFAULT false,
  first_dispatch_at timestamptz,
  retransmission_cutoff timestamptz,
  transmission_count integer NOT NULL DEFAULT 0,
  guard_snapshot jsonb NOT NULL,
  last_reconciled_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, obligation_id, id),
  UNIQUE (agency_id, task_id, id),
  UNIQUE (agency_id, obligation_id, attempt_no),
  FOREIGN KEY (agency_id, task_id, obligation_id) REFERENCES payment_obligations(agency_id, task_id, id),
  FOREIGN KEY (agency_id, task_id, mandate_version_id) REFERENCES mandate_versions(agency_id, task_id, id),
  FOREIGN KEY (agency_id, task_id, mandate_version_id, decision_request_id)
    REFERENCES decision_requests(agency_id, task_id, mandate_version_id, id)
);

CREATE TABLE IF NOT EXISTS payout_items (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  attempt_id uuid NOT NULL,
  payer_account_ref text NOT NULL CHECK (payer_account_ref='payer_sandbox_us'),
  provider_batch_id text,
  provider_item_id text,
  provider_transaction_id text,
  raw_status text,
  canonical_state text NOT NULL CHECK (canonical_state IN ('created','processing','success',
    'unclaimed','cancelled','failed','blocked')),
  fee_cents bigint CHECK (fee_cents >= 0),
  fee_currency text,
  binding_verified boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, attempt_id),
  FOREIGN KEY (agency_id, attempt_id) REFERENCES payment_attempts(agency_id, id)
);

CREATE TABLE IF NOT EXISTS provider_observations (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  attempt_id uuid NOT NULL,
  operation text NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT now(),
  raw_status text,
  response_digest text NOT NULL,
  redacted_response jsonb NOT NULL,
  protected_response_ciphertext bytea,
  binding_verified boolean NOT NULL,
  UNIQUE (agency_id, id),
  UNIQUE (agency_id, attempt_id, id),
  FOREIGN KEY (agency_id, attempt_id) REFERENCES payment_attempts(agency_id, id)
);

CREATE TABLE IF NOT EXISTS budget_entries (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  obligation_id uuid NOT NULL,
  attempt_id uuid NOT NULL,
  phase text NOT NULL CHECK (phase IN ('reservation','disposition')),
  kind text NOT NULL CHECK (kind IN ('reserve','consume','release')),
  principal_cents bigint NOT NULL CHECK (principal_cents > 0),
  reserved_delta bigint NOT NULL,
  consumed_delta bigint NOT NULL,
  proof_observation_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, attempt_id, phase),
  FOREIGN KEY (agency_id, obligation_id, attempt_id) REFERENCES payment_attempts(agency_id, obligation_id, id)
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  claimed_event_id text NOT NULL,
  transmission_id text NOT NULL,
  raw_body bytea NOT NULL CHECK (octet_length(raw_body) <= 65536),
  payload_digest text NOT NULL,
  headers jsonb NOT NULL,
  verification_state text NOT NULL CHECK (verification_state IN ('pending','verified','invalid','error')),
  verification_result jsonb,
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  payer_account_ref text NOT NULL CHECK (payer_account_ref='payer_sandbox_us'),
  provider_event_id text NOT NULL,
  delivery_id uuid NOT NULL,
  payload_digest text NOT NULL,
  event_type text NOT NULL,
  verified_at timestamptz NOT NULL,
  matched_attempt_id uuid,
  UNIQUE (payer_account_ref, provider_event_id),
  UNIQUE (agency_id, id),
  FOREIGN KEY (agency_id, delivery_id) REFERENCES webhook_deliveries(agency_id, id),
  FOREIGN KEY (agency_id, matched_attempt_id) REFERENCES payment_attempts(agency_id, id)
);

CREATE TABLE IF NOT EXISTS command_receipts (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  principal_user_id uuid NOT NULL,
  effective_user_id uuid NOT NULL,
  operation text NOT NULL,
  idempotency_key uuid NOT NULL,
  request_digest text NOT NULL,
  http_status integer NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, principal_user_id, effective_user_id, operation, idempotency_key),
  FOREIGN KEY (agency_id, principal_user_id) REFERENCES users(agency_id, id),
  FOREIGN KEY (agency_id, effective_user_id) REFERENCES users(agency_id, id)
);

CREATE TABLE IF NOT EXISTS tool_invocations (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  job_id uuid NOT NULL,
  tool_name text NOT NULL CHECK (tool_name IN ('propose_checks','inspect_evidence','request_correction','request_payout')),
  input_digest text NOT NULL,
  state text NOT NULL CHECK (state IN ('running','done','failed','stale')),
  interaction_id uuid,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, job_id, tool_name, input_digest),
  FOREIGN KEY (agency_id, job_id) REFERENCES outbox_events(agency_id, id)
);

CREATE TABLE IF NOT EXISTS demo_archives (
  id uuid PRIMARY KEY,
  agency_id uuid NOT NULL,
  completed_task_id uuid NOT NULL,
  bundle_digest text NOT NULL,
  archived_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agency_id, id)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id uuid PRIMARY KEY,
  sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  agency_id uuid NOT NULL REFERENCES agencies(id),
  principal_user_id uuid,
  effective_user_id uuid,
  service_actor text,
  event_type text NOT NULL,
  correlation_id uuid NOT NULL,
  references_json jsonb NOT NULL,
  details jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (agency_id, principal_user_id) REFERENCES users(agency_id, id),
  FOREIGN KEY (agency_id, effective_user_id) REFERENCES users(agency_id, id)
);
