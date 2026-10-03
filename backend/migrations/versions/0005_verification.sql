ALTER TABLE verification_jobs ADD COLUMN completion_digest text;
ALTER TABLE verification_jobs ADD CONSTRAINT verification_completion_digest CHECK (
  completion_digest IS NULL OR completion_digest ~ '^[0-9a-f]{64}$');
ALTER TABLE evidence_bundles ADD COLUMN manifest_json jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE FUNCTION freeze_verification_input() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'verification history cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF ROW(NEW.id,NEW.agency_id,NEW.task_id,NEW.delivery_id,NEW.inputs,NEW.input_digest,NEW.created_at)
     IS DISTINCT FROM ROW(OLD.id,OLD.agency_id,OLD.task_id,OLD.delivery_id,OLD.inputs,OLD.input_digest,OLD.created_at) THEN
    RAISE EXCEPTION 'verification inputs cannot change' USING ERRCODE='23514';
  END IF;
  IF OLD.completion_digest IS NOT NULL AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
    RAISE EXCEPTION 'verification completion cannot change' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER verification_input BEFORE UPDATE OR DELETE ON verification_jobs
  FOR EACH ROW EXECUTE FUNCTION freeze_verification_input();
REVOKE ALL ON FUNCTION freeze_verification_input() FROM PUBLIC;
