ALTER TABLE outbox_events ADD CONSTRAINT outbox_lease_check CHECK (
  (state='leased' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR
  (state<>'leased' AND lease_token IS NULL AND lease_until IS NULL));
ALTER TABLE outbox_events ADD CONSTRAINT outbox_json_check CHECK (
  jsonb_typeof(payload)='object' AND jsonb_typeof(stage_state)='object');

CREATE FUNCTION protect_outbox_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE stage record;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'outbox history cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF (to_jsonb(NEW)-ARRAY['stage_state','state','available_at','lease_token','lease_until',
                        'attempt_count','last_error_code','updated_at']) IS DISTINCT FROM
     (to_jsonb(OLD)-ARRAY['stage_state','state','available_at','lease_token','lease_until',
                        'attempt_count','last_error_code','updated_at']) OR
     NEW.attempt_count<OLD.attempt_count OR (OLD.state='done' AND NEW IS DISTINCT FROM OLD) THEN
    RAISE EXCEPTION 'job source/history cannot change or regress' USING ERRCODE='23514';
  END IF;
  FOR stage IN SELECT key,value FROM jsonb_each(OLD.stage_state) LOOP
    IF stage.value->>'status'='accepted' AND NEW.stage_state->stage.key IS DISTINCT FROM stage.value THEN
      RAISE EXCEPTION 'accepted stage output cannot change' USING ERRCODE='23514';
    END IF;
  END LOOP;
  RETURN NEW;
END;
$$;
CREATE TRIGGER freeze_job_source BEFORE UPDATE OR DELETE ON outbox_events
  FOR EACH ROW EXECUTE FUNCTION protect_outbox_source();
REVOKE ALL ON FUNCTION protect_outbox_source() FROM PUBLIC;
