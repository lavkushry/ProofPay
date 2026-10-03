-- Forward upgrade of the exact PR #4 schema; existing invalid rows abort atomically.
-- The design's verification_claim index needs a creation timestamp omitted by its DDL sketch.
ALTER TABLE verification_jobs ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE contractors ADD CONSTRAINT contractor_current_binding_fk
  FOREIGN KEY (agency_id,id,current_binding_id) REFERENCES recipient_bindings(agency_id,contractor_id,id);
ALTER TABLE agencies ADD CONSTRAINT agency_current_run_fk
  FOREIGN KEY (id,current_demo_run_id) REFERENCES demo_runs(agency_id,id);
ALTER TABLE briefs ADD CONSTRAINT brief_current_revision_fk
  FOREIGN KEY (agency_id,id,current_revision_id) REFERENCES brief_revisions(agency_id,brief_id,id);
ALTER TABLE mandates ADD CONSTRAINT mandate_current_version_fk
  FOREIGN KEY (agency_id,id,current_version_id) REFERENCES mandate_versions(agency_id,mandate_id,id);
ALTER TABLE deliveries ADD CONSTRAINT delivery_predecessor_fk
  FOREIGN KEY (agency_id,task_id,previous_delivery_id) REFERENCES deliveries(agency_id,task_id,id);
ALTER TABLE delivery_tasks ADD CONSTRAINT task_current_delivery_fk
  FOREIGN KEY (agency_id,id,current_delivery_id) REFERENCES deliveries(agency_id,task_id,id);
ALTER TABLE delivery_tasks ADD CONSTRAINT task_current_bundle_fk
  FOREIGN KEY (agency_id,id,current_bundle_id) REFERENCES evidence_bundles(agency_id,task_id,id);
ALTER TABLE ai_interactions ADD CONSTRAINT interaction_bundle_fk
  FOREIGN KEY (agency_id,bundle_id) REFERENCES evidence_bundles(agency_id,id);
ALTER TABLE payment_obligations ADD CONSTRAINT obligation_success_attempt_fk
  FOREIGN KEY (agency_id,id,success_attempt_id) REFERENCES payment_attempts(agency_id,obligation_id,id);
ALTER TABLE budget_entries ADD CONSTRAINT ledger_proof_fk
  FOREIGN KEY (agency_id,attempt_id,proof_observation_id) REFERENCES provider_observations(agency_id,attempt_id,id);
ALTER TABLE tool_invocations ADD CONSTRAINT tool_interaction_fk
  FOREIGN KEY (agency_id,interaction_id) REFERENCES ai_interactions(agency_id,id);
ALTER TABLE demo_archives ADD CONSTRAINT archive_task_fk
  FOREIGN KEY (agency_id,completed_task_id) REFERENCES delivery_tasks(agency_id,id);
ALTER TABLE demo_runs ADD CONSTRAINT run_featured_archive_fk
  FOREIGN KEY (agency_id,featured_archive_id) REFERENCES demo_archives(agency_id,id);

ALTER TABLE mandate_versions ADD CONSTRAINT approval_identity_check CHECK (
  (approved_at IS NULL AND approved_by IS NULL AND lifecycle_state='draft') OR
  (approved_at IS NOT NULL AND approved_by IS NOT NULL AND lifecycle_state<>'draft'));
ALTER TABLE evidence_results ADD CONSTRAINT result_size_check
  CHECK (octet_length(observations::text) <= 65536);
ALTER TABLE evidence_artifacts ADD CONSTRAINT artifact_size_check
  CHECK (octet_length(content) <= CASE WHEN media_type='image/png' THEN 524288 ELSE 65536 END);
ALTER TABLE payment_attempts ADD CONSTRAINT attempt_resolution_check CHECK (unresolved OR successful OR nonpayment_confirmed);
ALTER TABLE payment_attempts ADD CONSTRAINT attempt_success_resolved_check CHECK (NOT (successful AND unresolved));
ALTER TABLE payment_attempts ADD CONSTRAINT attempt_disposition_check CHECK (NOT (successful AND nonpayment_confirmed));
ALTER TABLE payment_attempts ADD CONSTRAINT attempt_state_check CHECK (
  (state='success' AND successful) OR (state<>'success' AND NOT successful));
ALTER TABLE payout_items ADD CONSTRAINT matched_item_success_check CHECK (
  canonical_state<>'success' OR (provider_item_id IS NOT NULL AND raw_status='SUCCESS' AND binding_verified));
ALTER TABLE budget_entries ADD CONSTRAINT ledger_delta_check CHECK (
  (phase='reservation' AND kind='reserve' AND reserved_delta=principal_cents AND consumed_delta=0) OR
  (phase='disposition' AND kind='consume' AND reserved_delta=-principal_cents AND consumed_delta=principal_cents) OR
  (phase='disposition' AND kind='release' AND reserved_delta=-principal_cents AND consumed_delta=0));
ALTER TABLE audit_log ADD CONSTRAINT audit_actor_check CHECK (principal_user_id IS NOT NULL OR service_actor IS NOT NULL);

CREATE UNIQUE INDEX one_active_demo_run ON demo_runs(agency_id) WHERE state='active';
CREATE UNIQUE INDEX one_current_approved_version ON mandate_versions(agency_id,mandate_id) WHERE lifecycle_state='approved';
CREATE UNIQUE INDEX one_unresolved_attempt ON payment_attempts(agency_id,obligation_id) WHERE unresolved;
CREATE UNIQUE INDEX one_successful_attempt ON payment_attempts(agency_id,obligation_id) WHERE successful;
CREATE UNIQUE INDEX provider_item_once ON payout_items(payer_account_ref,provider_item_id) WHERE provider_item_id IS NOT NULL;

CREATE INDEX task_queue ON delivery_tasks(agency_id,demo_run_id,state,updated_at DESC,id);
CREATE INDEX brief_history ON brief_revisions(agency_id,brief_id,revision DESC);
CREATE INDEX mandate_history ON mandate_versions(agency_id,mandate_id,version DESC);
CREATE INDEX delivery_history ON deliveries(agency_id,task_id,sequence DESC);
CREATE INDEX verification_claim ON verification_jobs(state,lease_until,created_at)
  WHERE state IN ('queued','running');
CREATE INDEX evidence_history ON evidence_bundles(agency_id,task_id,created_at DESC);
CREATE INDEX evidence_bytes ON evidence_artifacts(agency_id,bundle_id,check_id);
CREATE INDEX ai_by_job ON ai_interactions(agency_id,job_id,created_at);
CREATE INDEX corrections_by_task ON corrections(agency_id,task_id,created_at);
CREATE INDEX release_history ON decision_requests(agency_id,task_id,created_at);
CREATE INDEX active_payments ON payment_attempts(agency_id,last_reconciled_at,created_at)
  WHERE unresolved;
CREATE INDEX attempts_by_task ON payment_attempts(agency_id,task_id,attempt_no);
CREATE INDEX provider_history ON provider_observations(agency_id,attempt_id,observed_at,id);
CREATE INDEX ledger_by_obligation ON budget_entries(agency_id,obligation_id,created_at,id);
CREATE INDEX outbox_ready ON outbox_events(available_at,id) WHERE state='ready';
CREATE INDEX outbox_expired ON outbox_events(lease_until,id) WHERE state='leased';
CREATE INDEX quarantine_pending ON webhook_deliveries(received_at,id)
  WHERE verification_state IN ('pending','error');
CREATE INDEX quarantine_claimed_id ON webhook_deliveries(agency_id,claimed_event_id);
CREATE INDEX audit_by_task_refs ON audit_log USING gin(references_json);
CREATE INDEX audit_timeline ON audit_log(agency_id,created_at,sequence);
CREATE INDEX session_expiry ON sessions(expires_at) WHERE revoked_at IS NULL;

CREATE FUNCTION deny_source_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'immutable source: %', TG_TABLE_NAME USING ERRCODE='23514';
END;
$$;

DO $$
DECLARE source_table text;
BEGIN
  FOREACH source_table IN ARRAY ARRAY[
    'recipient_bindings','fixture_manifests','artifact_versions','brief_revisions',
    'deliveries','evidence_bundles','evidence_results','evidence_artifacts',
    'ai_interactions','corrections','review_resolutions','provider_observations',
    'budget_entries','command_receipts','demo_archives','audit_log'
  ] LOOP
    EXECUTE format('CREATE TRIGGER freeze_source BEFORE UPDATE OR DELETE ON %I
      FOR EACH ROW EXECUTE FUNCTION deny_source_mutation()', source_table);
  END LOOP;
END;
$$;

CREATE FUNCTION freeze_approved_mandate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'mandate version history cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF OLD.lifecycle_state<>'draft' AND
     (to_jsonb(NEW)-'lifecycle_state') IS DISTINCT FROM
     (to_jsonb(OLD)-'lifecycle_state') THEN
    RAISE EXCEPTION 'approved snapshot cannot change' USING ERRCODE='23514';
  END IF;
  IF OLD.lifecycle_state<>'draft' AND NEW.lifecycle_state<>OLD.lifecycle_state AND
     NOT (OLD.lifecycle_state='approved' AND
          NEW.lifecycle_state IN ('expired','superseded','exhausted')) THEN
    RAISE EXCEPTION 'invalid authority transition' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_mandate BEFORE UPDATE OR DELETE ON mandate_versions
  FOR EACH ROW EXECUTE FUNCTION freeze_approved_mandate();

CREATE FUNCTION freeze_approved_checks() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_state text; parent_id uuid; parent_agency uuid;
BEGIN
  IF TG_OP='DELETE' THEN
    parent_id:=OLD.mandate_version_id; parent_agency:=OLD.agency_id;
  ELSE
    parent_id:=NEW.mandate_version_id; parent_agency:=NEW.agency_id;
  END IF;
  IF TG_OP='UPDATE' AND
     ROW(NEW.agency_id,NEW.mandate_version_id,NEW.id) IS DISTINCT FROM
     ROW(OLD.agency_id,OLD.mandate_version_id,OLD.id) THEN
    RAISE EXCEPTION 'check identity cannot move' USING ERRCODE='23514';
  END IF;
  SELECT lifecycle_state INTO parent_state FROM mandate_versions
    WHERE agency_id=parent_agency AND id=parent_id FOR UPDATE;
  IF parent_state IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'approved checks cannot change' USING ERRCODE='23514';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_checks BEFORE INSERT OR UPDATE OR DELETE ON acceptance_checks
  FOR EACH ROW EXECUTE FUNCTION freeze_approved_checks();

CREATE FUNCTION require_three_approved_checks() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE approved_count integer; current_state text;
BEGIN
  SELECT lifecycle_state INTO current_state FROM mandate_versions WHERE id=NEW.id;
  IF current_state='approved' THEN
    SELECT count(*) INTO approved_count FROM acceptance_checks
      WHERE agency_id=NEW.agency_id AND mandate_version_id=NEW.id AND approved;
    IF approved_count<>3 THEN
      RAISE EXCEPTION 'approved mandate needs three approved checks' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER three_checks AFTER INSERT OR UPDATE ON mandate_versions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
  EXECUTE FUNCTION require_three_approved_checks();

CREATE FUNCTION protect_attempt_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'payment attempt cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF ROW(NEW.agency_id,NEW.task_id,NEW.obligation_id,NEW.mandate_version_id,
         NEW.decision_request_id,NEW.attempt_no,NEW.principal_cents,NEW.currency,
         NEW.sender_batch_id,NEW.sender_item_id,NEW.request_ciphertext,NEW.request_digest)
     IS DISTINCT FROM
     ROW(OLD.agency_id,OLD.task_id,OLD.obligation_id,OLD.mandate_version_id,
         OLD.decision_request_id,OLD.attempt_no,OLD.principal_cents,OLD.currency,
         OLD.sender_batch_id,OLD.sender_item_id,OLD.request_ciphertext,OLD.request_digest) THEN
    RAISE EXCEPTION 'attempt identity/payload cannot change' USING ERRCODE='23514';
  END IF;
  IF (OLD.successful AND NOT NEW.successful) OR
     (OLD.nonpayment_confirmed AND NOT NEW.nonpayment_confirmed) OR
     (NOT OLD.unresolved AND NEW.unresolved) OR
     NEW.transmission_count<OLD.transmission_count OR
     (OLD.first_dispatch_at IS NOT NULL AND
       NEW.first_dispatch_at IS DISTINCT FROM OLD.first_dispatch_at) THEN
    RAISE EXCEPTION 'attempt history cannot reopen or regress' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_attempt BEFORE UPDATE OR DELETE ON payment_attempts
  FOR EACH ROW EXECUTE FUNCTION protect_attempt_identity();

CREATE FUNCTION require_verified_webhook() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original webhook_deliveries%ROWTYPE;
BEGIN
  SELECT * INTO original FROM webhook_deliveries
    WHERE agency_id=NEW.agency_id AND id=NEW.delivery_id FOR UPDATE;
  IF original.verification_state IS DISTINCT FROM 'verified' OR
     original.claimed_event_id IS DISTINCT FROM NEW.provider_event_id OR
     original.payload_digest IS DISTINCT FROM NEW.payload_digest THEN
    RAISE EXCEPTION 'canonical event needs matching verified delivery' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER verified_event BEFORE INSERT ON webhook_events
  FOR EACH ROW EXECUTE FUNCTION require_verified_webhook();

-- Mixed source/projection rows allow only the documented projection updates.
CREATE FUNCTION protect_webhook_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['verification_state','verification_result'])
    IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['verification_state','verification_result']) THEN
    RAISE EXCEPTION 'webhook quarantine source cannot change' USING ERRCODE='23514';
  END IF;
  IF OLD.verification_state='verified' AND NEW.verification_state<>'verified' THEN
    RAISE EXCEPTION 'verified delivery cannot regress' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_webhook_delivery BEFORE UPDATE OR DELETE ON webhook_deliveries
  FOR EACH ROW EXECUTE FUNCTION protect_webhook_delivery();

CREATE FUNCTION protect_webhook_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' OR (to_jsonb(NEW)-'matched_attempt_id') IS DISTINCT FROM (to_jsonb(OLD)-'matched_attempt_id')
    OR (OLD.matched_attempt_id IS NOT NULL AND NEW.matched_attempt_id IS DISTINCT FROM OLD.matched_attempt_id) THEN
    RAISE EXCEPTION 'verified event identity cannot change' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_webhook_event BEFORE UPDATE OR DELETE ON webhook_events
  FOR EACH ROW EXECUTE FUNCTION protect_webhook_event();

CREATE FUNCTION protect_decision_request() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['state','evaluation_generation'])
    IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','evaluation_generation'])
    OR NEW.evaluation_generation<OLD.evaluation_generation THEN
    RAISE EXCEPTION 'decision input cannot change or regress' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_decision BEFORE UPDATE OR DELETE ON decision_requests
  FOR EACH ROW EXECUTE FUNCTION protect_decision_request();
