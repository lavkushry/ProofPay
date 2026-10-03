-- Provision the LOGIN roles before migrations (backend.provision_db).
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO proofpay_api, proofpay_executor;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, proofpay_api, proofpay_executor;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, proofpay_api, proofpay_executor;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, proofpay_api, proofpay_executor;

-- Explicit lists prevent future tables from silently receiving runtime authority.
GRANT SELECT ON agencies, users, contractors, sessions, demo_runs, fixture_manifests,
  artifact_versions, briefs, brief_revisions, delivery_tasks, mandates, mandate_versions,
  acceptance_checks, deliveries, verification_jobs, evidence_bundles, evidence_results,
  evidence_artifacts, outbox_events, ai_interactions, compilations, corrections,
  review_resolutions, decision_requests, payment_obligations, payout_items,
  budget_entries, webhook_deliveries, webhook_events, command_receipts,
  tool_invocations, demo_archives, audit_log, alembic_version TO proofpay_api;
GRANT SELECT (id,agency_id,contractor_id,receiver_hash,key_version,confirmed_at,created_at)
  ON recipient_bindings TO proofpay_api;
GRANT SELECT (id,agency_id,task_id,obligation_id,mandate_version_id,decision_request_id,
  attempt_no,principal_cents,currency,sender_batch_id,sender_item_id,request_digest,
  state,unresolved,nonpayment_confirmed,successful,first_dispatch_at,retransmission_cutoff,
  transmission_count,guard_snapshot,last_reconciled_at,created_at) ON payment_attempts TO proofpay_api;
GRANT SELECT (id,agency_id,attempt_id,operation,observed_at,raw_status,response_digest,
  redacted_response,binding_verified) ON provider_observations TO proofpay_api;

GRANT INSERT ON sessions, demo_runs, briefs, brief_revisions, delivery_tasks, mandates,
  mandate_versions, acceptance_checks, deliveries, verification_jobs, evidence_bundles,
  evidence_results, evidence_artifacts, outbox_events, ai_interactions, compilations,
  corrections, review_resolutions, decision_requests, webhook_deliveries,
  command_receipts, tool_invocations, demo_archives, audit_log TO proofpay_api;
GRANT INSERT (id,agency_id,task_id,currency) ON payment_obligations TO proofpay_api;
GRANT UPDATE (current_demo_run_id) ON agencies TO proofpay_api;
GRANT UPDATE (effective_user_id,cookie_hash,csrf_nonce,expires_at,revoked_at) ON sessions TO proofpay_api;
GRANT UPDATE (state,featured_archive_id) ON demo_runs TO proofpay_api;
GRANT UPDATE (current_revision_id) ON briefs TO proofpay_api;
GRANT UPDATE (state,current_delivery_id,current_bundle_id,review_required,hold_reasons,version,updated_at)
  ON delivery_tasks TO proofpay_api;
GRANT UPDATE (current_version_id) ON mandates TO proofpay_api;
GRANT UPDATE ON mandate_versions, acceptance_checks, verification_jobs, compilations, outbox_events TO proofpay_api;
GRANT UPDATE (state,evaluation_generation) ON decision_requests TO proofpay_api;
GRANT UPDATE (state,interaction_id,result) ON tool_invocations TO proofpay_api;
GRANT USAGE ON SEQUENCE audit_log_sequence_seq TO proofpay_api;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO proofpay_executor;
GRANT INSERT ON payment_attempts, payout_items, provider_observations, budget_entries,
  webhook_events, outbox_events, audit_log TO proofpay_executor;
GRANT UPDATE ON payment_attempts, payout_items, payment_obligations, outbox_events TO proofpay_executor;
GRANT UPDATE (reserved_cents,consumed_cents) ON agencies TO proofpay_executor;
GRANT UPDATE (state,review_required,hold_reasons,version,updated_at) ON delivery_tasks TO proofpay_executor;
GRANT UPDATE (lifecycle_state) ON mandate_versions TO proofpay_executor;
GRANT UPDATE (state,evaluation_generation) ON decision_requests TO proofpay_executor;
GRANT UPDATE (verification_state,verification_result) ON webhook_deliveries TO proofpay_executor;
GRANT UPDATE (matched_attempt_id) ON webhook_events TO proofpay_executor;
GRANT USAGE ON SEQUENCE audit_log_sequence_seq TO proofpay_executor;

-- Task state is shared with API verification; financial transitions require the executor.
CREATE FUNCTION protect_financial_task_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE was_financial boolean := false; is_financial boolean;
BEGIN
  is_financial := NEW.state IN ('payment_initiated','reconciling','paid','failed','unclaimed','cancelled');
  IF TG_OP='UPDATE' THEN
    IF NEW.state=OLD.state THEN RETURN NEW; END IF;
    was_financial := OLD.state IN ('payment_initiated','reconciling','paid','failed','unclaimed','cancelled');
  END IF;
  IF (is_financial OR was_financial)
    AND NOT pg_has_role(current_user,'proofpay_executor','MEMBER')
    AND current_user<>(SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid=TG_RELID) THEN
    RAISE EXCEPTION 'financial task state requires executor' USING ERRCODE='42501';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER financial_task_state BEFORE INSERT OR UPDATE ON delivery_tasks
  FOR EACH ROW EXECUTE FUNCTION protect_financial_task_state();
