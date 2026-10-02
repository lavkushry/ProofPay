import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, DateTime,
    ForeignKey, LargeBinary, UniqueConstraint, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, CHAR, JSON
from backend.app.database import Base

# Universal UUID type that works across both SQLite and PostgreSQL
class GUID(TypeDecorator):
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(value) if not isinstance(value, uuid.UUID) else value

# Universal JSON type
UniversalJSON = JSON

def utc_now():
    return datetime.now(timezone.utc)

class Agency(Base):
    __tablename__ = "agencies"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    advisory_lock_key = Column(BigInteger, unique=True, nullable=False)
    principal_limit_cents = Column(BigInteger, nullable=False)
    reserved_cents = Column(BigInteger, default=0, nullable=False)
    consumed_cents = Column(BigInteger, default=0, nullable=False)
    current_demo_run_id = Column(GUID, nullable=True)

class User(Base):
    __tablename__ = "users"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    role = Column(String, nullable=False) # 'owner', 'contractor', 'judge'
    display_name = Column(String, nullable=False)

class Contractor(Base):
    __tablename__ = "contractors"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    user_id = Column(GUID, ForeignKey("users.id"), nullable=False)
    recipient_ref = Column(String, nullable=False) # 'contractor_maya', 'contractor_leo'
    display_name = Column(String, nullable=False)
    current_binding_id = Column(GUID, nullable=True)

class RecipientBinding(Base):
    __tablename__ = "recipient_bindings"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    contractor_id = Column(GUID, ForeignKey("contractors.id"), nullable=False)
    receiver_ciphertext = Column(LargeBinary, nullable=False)
    receiver_hash = Column(String(64), nullable=False)
    key_version = Column(String, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class SessionModel(Base):
    __tablename__ = "sessions"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    principal_user_id = Column(GUID, ForeignKey("users.id"), nullable=False)
    effective_user_id = Column(GUID, ForeignKey("users.id"), nullable=False)
    cookie_hash = Column(String, unique=True, nullable=False)
    csrf_nonce = Column(String, nullable=False)
    is_judge = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

class DemoRun(Base):
    __tablename__ = "demo_runs"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    state = Column(String, default="active", nullable=False) # 'active', 'archived'
    featured_archive_id = Column(GUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class FixtureManifest(Base):
    __tablename__ = "fixture_manifests"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    fixture_ref = Column(String, default="checkout_fixture", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    digest = Column(String(64), nullable=False)
    manifest = Column(UniversalJSON, nullable=False)

class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    manifest_id = Column(GUID, ForeignKey("fixture_manifests.id"), nullable=False)
    artifact_ref = Column(String, nullable=False)
    family = Column(String, nullable=False) # 'responsive_css', 'api_endpoint', 'keyboard_accessibility'
    digest = Column(String(64), nullable=False)
    relative_path = Column(String, nullable=False)

class Brief(Base):
    __tablename__ = "briefs"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    current_revision_id = Column(GUID, nullable=True)
    created_by = Column(GUID, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class BriefRevision(Base):
    __tablename__ = "brief_revisions"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    brief_id = Column(GUID, ForeignKey("briefs.id"), nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    title = Column(String(160), nullable=False)
    body = Column(String(4000), nullable=False)
    family = Column(String, nullable=False)
    manifest_id = Column(GUID, ForeignKey("fixture_manifests.id"), nullable=False)
    proposed_terms = Column(UniversalJSON, nullable=False)
    digest = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class DeliveryTask(Base):
    __tablename__ = "delivery_tasks"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    demo_run_id = Column(GUID, ForeignKey("demo_runs.id"), nullable=False)
    brief_id = Column(GUID, ForeignKey("briefs.id"), nullable=False)
    state = Column(String, default="brief_captured", nullable=False)
    current_delivery_id = Column(GUID, nullable=True)
    current_bundle_id = Column(GUID, nullable=True)
    review_required = Column(Boolean, default=False, nullable=False)
    hold_reasons = Column(UniversalJSON, default=list, nullable=False)
    version = Column(BigInteger, default=1, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class Mandate(Base):
    __tablename__ = "mandates"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, ForeignKey("delivery_tasks.id"), nullable=False)
    current_version_id = Column(GUID, nullable=True)

class MandateVersion(Base):
    __tablename__ = "mandate_versions"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    mandate_id = Column(GUID, ForeignKey("mandates.id"), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    brief_revision_id = Column(GUID, ForeignKey("brief_revisions.id"), nullable=False)
    compilation_id = Column(GUID, nullable=False)
    contractor_id = Column(GUID, nullable=False)
    recipient_binding_id = Column(GUID, nullable=False)
    lifecycle_state = Column(String, default="draft", nullable=False) # 'draft', 'approved', 'expired', 'superseded', 'exhausted'
    amount_cents = Column(BigInteger, nullable=False)
    principal_cap_cents = Column(BigInteger, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    public_payload = Column(UniversalJSON, nullable=False)
    payload_digest = Column(String(64), nullable=False)
    approved_by = Column(GUID, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class AcceptanceCheck(Base):
    __tablename__ = "acceptance_checks"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, ForeignKey("mandate_versions.id"), nullable=False)
    check_id = Column(String, nullable=False) # 'C01', 'C02', 'C03'
    template_type = Column(String, nullable=False)
    params = Column(UniversalJSON, nullable=False)
    compiled_by = Column(String, default="ai", nullable=False)
    approved = Column(Boolean, default=False, nullable=False)

class Delivery(Base):
    __tablename__ = "deliveries"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, ForeignKey("mandate_versions.id"), nullable=False)
    artifact_version_id = Column(GUID, ForeignKey("artifact_versions.id"), nullable=False)
    artifact_digest = Column(String(64), nullable=False)
    mandate_digest = Column(String(64), nullable=False)
    submitted_by = Column(GUID, ForeignKey("users.id"), nullable=False)
    claim = Column(String(4000), nullable=False)
    claim_digest = Column(String(64), nullable=False)
    sequence = Column(Integer, default=1, nullable=False)
    previous_delivery_id = Column(GUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class VerificationJob(Base):
    __tablename__ = "verification_jobs"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    delivery_id = Column(GUID, ForeignKey("deliveries.id"), nullable=False)
    state = Column(String, default="queued", nullable=False) # 'queued', 'running', 'completed', 'error', 'stale'
    inputs = Column(UniversalJSON, nullable=False)
    input_digest = Column(String(64), nullable=False)
    worker_id = Column(String, nullable=True)
    lease_token = Column(GUID, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    lease_attempt = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class EvidenceBundle(Base):
    __tablename__ = "evidence_bundles"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    delivery_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    verification_job_id = Column(GUID, nullable=False)
    artifact_digest = Column(String(64), nullable=False)
    mandate_digest = Column(String(64), nullable=False)
    bundle_digest = Column(String(64), nullable=False)
    manifest_id = Column(GUID, ForeignKey("fixture_manifests.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class EvidenceResult(Base):
    __tablename__ = "evidence_results"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, ForeignKey("evidence_bundles.id"), nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    acceptance_check_id = Column(GUID, ForeignKey("acceptance_checks.id"), nullable=False)
    outcome = Column(String, nullable=False) # 'pass', 'fail', 'error'
    observations = Column(UniversalJSON, nullable=False)
    result_digest = Column(String(64), nullable=False)
    completed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, ForeignKey("evidence_bundles.id"), nullable=False)
    check_id = Column(String, nullable=True)
    media_type = Column(String, nullable=False) # 'image/png', 'application/json'
    digest = Column(String(64), nullable=False)
    content = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class AIInteraction(Base):
    __tablename__ = "ai_interactions"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    job_id = Column(GUID, nullable=False)
    stage = Column(String, nullable=False) # 'compiler', 'reviewer'
    brief_revision_id = Column(GUID, nullable=True)
    bundle_id = Column(GUID, nullable=True)
    model_ref = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    schema_version = Column(String, nullable=False)
    input_digest = Column(String(64), nullable=False)
    input_refs = Column(UniversalJSON, nullable=False)
    output = Column(UniversalJSON, nullable=True)
    output_digest = Column(String(64), nullable=True)
    validated = Column(Boolean, default=False, nullable=False)
    error_code = Column(String, nullable=True)
    usage = Column(UniversalJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class Compilation(Base):
    __tablename__ = "compilations"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    brief_revision_id = Column(GUID, ForeignKey("brief_revisions.id"), nullable=False)
    job_id = Column(GUID, nullable=False)
    status = Column(String, default="queued", nullable=False) # 'queued', 'running', 'ready', 'ambiguous', 'failed'
    interaction_id = Column(GUID, nullable=True)
    proposal = Column(UniversalJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class Correction(Base):
    __tablename__ = "corrections"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    delivery_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    review_interaction_id = Column(GUID, ForeignKey("ai_interactions.id"), nullable=False)
    contractor_message = Column(String(2000), nullable=False)
    evidence_refs = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class ReviewResolution(Base):
    __tablename__ = "review_resolutions"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    review_interaction_id = Column(GUID, ForeignKey("ai_interactions.id"), nullable=False)
    resolved_by = Column(GUID, ForeignKey("users.id"), nullable=False)
    rationale = Column(String(1000), nullable=False)
    evidence_refs = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class DecisionRequest(Base):
    __tablename__ = "decision_requests"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    source = Column(String, default="ai", nullable=False) # 'ai', 'owner_resolution', 'owner_reevaluation'
    review_interaction_id = Column(GUID, ForeignKey("ai_interactions.id"), nullable=False)
    state = Column(String, default="queued", nullable=False) # 'queued', 'held', 'deduplicated'
    evaluation_generation = Column(Integer, default=1, nullable=False)
    request_digest = Column(String(64), nullable=False)
    evidence_refs = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class PaymentObligation(Base):
    __tablename__ = "payment_obligations"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, ForeignKey("delivery_tasks.id"), unique=True, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    next_attempt_no = Column(Integer, default=1, nullable=False)
    success_attempt_id = Column(GUID, nullable=True)
    reserved_cents = Column(BigInteger, default=0, nullable=False)
    consumed_cents = Column(BigInteger, default=0, nullable=False)

class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    obligation_id = Column(GUID, ForeignKey("payment_obligations.id"), nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    decision_request_id = Column(GUID, ForeignKey("decision_requests.id"), nullable=False)
    attempt_no = Column(Integer, nullable=False)
    principal_cents = Column(BigInteger, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    sender_batch_id = Column(String(256), unique=True, nullable=False)
    sender_item_id = Column(String(63), unique=True, nullable=False)
    request_ciphertext = Column(LargeBinary, nullable=False)
    request_digest = Column(String(64), nullable=False)
    state = Column(String, default="prepared", nullable=False) # 'prepared', 'dispatching', 'unknown', 'processing', 'unclaimed', 'success', 'failed', 'cancelled', 'blocked'
    unresolved = Column(Boolean, default=True, nullable=False)
    nonpayment_confirmed = Column(Boolean, default=False, nullable=False)
    successful = Column(Boolean, default=False, nullable=False)
    first_dispatch_at = Column(DateTime(timezone=True), nullable=True)
    retransmission_cutoff = Column(DateTime(timezone=True), nullable=True)
    transmission_count = Column(Integer, default=0, nullable=False)
    guard_snapshot = Column(UniversalJSON, nullable=False)
    last_reconciled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class PayoutItem(Base):
    __tablename__ = "payout_items"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    attempt_id = Column(GUID, ForeignKey("payment_attempts.id"), unique=True, nullable=False)
    payer_account_ref = Column(String, default="payer_sandbox_us", nullable=False)
    provider_batch_id = Column(String, nullable=True)
    provider_item_id = Column(String, nullable=True)
    provider_transaction_id = Column(String, nullable=True)
    raw_status = Column(String, nullable=True)
    canonical_state = Column(String, default="created", nullable=False) # 'created', 'processing', 'success', 'unclaimed', 'cancelled', 'failed', 'blocked'
    fee_cents = Column(BigInteger, nullable=True)
    fee_currency = Column(String, nullable=True)
    binding_verified = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class ProviderObservation(Base):
    __tablename__ = "provider_observations"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    attempt_id = Column(GUID, ForeignKey("payment_attempts.id"), nullable=False)
    operation = Column(String, nullable=False)
    observed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    raw_status = Column(String, nullable=True)
    response_digest = Column(String(64), nullable=False)
    redacted_response = Column(UniversalJSON, nullable=False)
    protected_response_ciphertext = Column(LargeBinary, nullable=True)
    binding_verified = Column(Boolean, default=False, nullable=False)

class BudgetEntry(Base):
    __tablename__ = "budget_entries"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    obligation_id = Column(GUID, nullable=False)
    attempt_id = Column(GUID, ForeignKey("payment_attempts.id"), nullable=False)
    phase = Column(String, nullable=False) # 'reservation', 'disposition'
    kind = Column(String, nullable=False) # 'reserve', 'consume', 'release'
    principal_cents = Column(BigInteger, nullable=False)
    reserved_delta = Column(BigInteger, nullable=False)
    consumed_delta = Column(BigInteger, nullable=False)
    proof_observation_id = Column(GUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    task_id = Column(GUID, nullable=True)
    event_type = Column(String, nullable=False)
    dedup_key = Column(String, unique=True, nullable=False)
    payload = Column(UniversalJSON, nullable=False)
    stage_state = Column(UniversalJSON, default=dict, nullable=False)
    state = Column(String, default="ready", nullable=False) # 'ready', 'leased', 'done', 'failed', 'held'
    available_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    lease_token = Column(GUID, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    last_error_code = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class CommandReceipt(Base):
    __tablename__ = "command_receipts"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, nullable=False)
    principal_user_id = Column(GUID, ForeignKey("users.id"), nullable=False)
    effective_user_id = Column(GUID, ForeignKey("users.id"), nullable=False)
    operation = Column(String, nullable=False)
    idempotency_key = Column(GUID, nullable=False)
    request_digest = Column(String(64), nullable=False)
    http_status = Column(Integer, nullable=False)
    response = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    agency_id = Column(GUID, ForeignKey("agencies.id"), nullable=False)
    principal_user_id = Column(GUID, ForeignKey("users.id"), nullable=True)
    effective_user_id = Column(GUID, ForeignKey("users.id"), nullable=True)
    service_actor = Column(String, nullable=True)
    event_type = Column(String, nullable=False)
    correlation_id = Column(GUID, nullable=False)
    references_json = Column(UniversalJSON, nullable=False)
    details = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
