"""Explicit mappings for the PostgreSQL schema managed by Alembic.

SQLite supports unit tests only. PostgreSQL-only checks and indexes remain
visible in metadata and are verified against the migrated database in CI.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Text, String, Integer, SmallInteger, BigInteger, Boolean, DateTime,
    ForeignKeyConstraint, LargeBinary, UniqueConstraint, CheckConstraint,
    Index, Identity, FetchedValue, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import deferred
from sqlalchemy.types import TypeDecorator, CHAR, JSON

from backend.app.database import Base


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
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


UniversalJSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


def utc_now():
    return datetime.now(timezone.utc)



class Agency(Base):
    __tablename__ = 'agencies'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    name = Column(Text, nullable=False)
    advisory_lock_key = Column(BigInteger, nullable=False)
    principal_limit_cents = Column(BigInteger, nullable=False)
    reserved_cents = Column(BigInteger, default=0, server_default=text('0'), nullable=False)
    consumed_cents = Column(BigInteger, default=0, server_default=text('0'), nullable=False)
    current_demo_run_id = Column(GUID, nullable=True)
    __table_args__ = (
        UniqueConstraint('advisory_lock_key'),
        CheckConstraint('principal_limit_cents > 0'),
        CheckConstraint('reserved_cents >= 0'),
        CheckConstraint('consumed_cents >= 0'),
        CheckConstraint('reserved_cents + consumed_cents <= principal_limit_cents'),
        ForeignKeyConstraint(['id', 'current_demo_run_id'], ['demo_runs.agency_id', 'demo_runs.id'], name='agency_current_run_fk', use_alter=True),
    )


class User(Base):
    __tablename__ = 'users'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    role = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        CheckConstraint("role IN ('owner','contractor','judge')"),
        UniqueConstraint(*['agency_id', 'id']),
    )


class Contractor(Base):
    __tablename__ = 'contractors'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    user_id = Column(GUID, nullable=False)
    recipient_ref = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    current_binding_id = Column(GUID, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        CheckConstraint("recipient_ref IN ('contractor_maya','contractor_leo')"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'recipient_ref']),
        UniqueConstraint(*['agency_id', 'user_id']),
        ForeignKeyConstraint(['agency_id', 'user_id'], ['users.agency_id', 'users.id']),
        ForeignKeyConstraint(['agency_id', 'id', 'current_binding_id'], ['recipient_bindings.agency_id', 'recipient_bindings.contractor_id', 'recipient_bindings.id'], name='contractor_current_binding_fk', use_alter=True),
    )


class RecipientBinding(Base):
    __tablename__ = 'recipient_bindings'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    contractor_id = Column(GUID, nullable=False)
    receiver_ciphertext = deferred(Column(LargeBinary, nullable=False))
    receiver_hash = Column(Text, nullable=False)
    key_version = Column(Text, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("receiver_hash ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'contractor_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'contractor_id'], ['contractors.agency_id', 'contractors.id']),
    )


class SessionModel(Base):
    __tablename__ = 'sessions'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    principal_user_id = Column(GUID, nullable=False)
    effective_user_id = Column(GUID, nullable=False)
    cookie_hash = Column(Text, nullable=False)
    csrf_nonce = Column(Text, nullable=False)
    is_judge = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint('cookie_hash'),
        ForeignKeyConstraint(['agency_id', 'principal_user_id'], ['users.agency_id', 'users.id']),
        ForeignKeyConstraint(['agency_id', 'effective_user_id'], ['users.agency_id', 'users.id']),
        Index('session_expiry', 'expires_at', postgresql_where=text('revoked_at IS NULL')).ddl_if(dialect="postgresql"),
    )


class DemoRun(Base):
    __tablename__ = 'demo_runs'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    state = Column(Text, default='active', nullable=False)
    featured_archive_id = Column(GUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        CheckConstraint("state IN ('active','archived')"),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'featured_archive_id'], ['demo_archives.agency_id', 'demo_archives.id'], name='run_featured_archive_fk', use_alter=True),
        Index('one_active_demo_run', 'agency_id', unique=True, postgresql_where=text("state='active'")).ddl_if(dialect="postgresql"),
    )


class FixtureManifest(Base):
    __tablename__ = 'fixture_manifests'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    fixture_ref = Column(Text, default='checkout_fixture', nullable=False)
    version = Column(Integer, default=1, nullable=False)
    digest = Column(Text, nullable=False)
    manifest = Column(UniversalJSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        CheckConstraint("fixture_ref='checkout_fixture'"),
        CheckConstraint('version > 0'),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        CheckConstraint("jsonb_typeof(manifest)='object'").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'fixture_ref', 'version']),
    )


class ArtifactVersion(Base):
    __tablename__ = 'artifact_versions'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    manifest_id = Column(GUID, nullable=False)
    artifact_ref = Column(Text, nullable=False)
    family = Column(Text, nullable=False)
    digest = Column(Text, nullable=False)
    relative_path = Column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint("family IN ('responsive_css','api_endpoint','keyboard_accessibility')"),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'artifact_ref']),
        ForeignKeyConstraint(['agency_id', 'manifest_id'], ['fixture_manifests.agency_id', 'fixture_manifests.id']),
    )


class Brief(Base):
    __tablename__ = 'briefs'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    current_revision_id = Column(GUID, nullable=True)
    created_by = Column(GUID, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'created_by'], ['users.agency_id', 'users.id']),
        ForeignKeyConstraint(['agency_id', 'id', 'current_revision_id'], ['brief_revisions.agency_id', 'brief_revisions.brief_id', 'brief_revisions.id'], name='brief_current_revision_fk', use_alter=True),
    )


class BriefRevision(Base):
    __tablename__ = 'brief_revisions'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    brief_id = Column(GUID, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    family = Column(Text, nullable=False)
    manifest_id = Column(GUID, nullable=False)
    proposed_terms = Column(UniversalJSON, nullable=False)
    digest = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint('revision > 0'),
        CheckConstraint('length(title) BETWEEN 1 AND 160'),
        CheckConstraint('length(body) BETWEEN 1 AND 4000'),
        CheckConstraint("family IN ('responsive_css','api_endpoint','keyboard_accessibility')"),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'brief_id', 'id']),
        UniqueConstraint(*['agency_id', 'brief_id', 'revision']),
        ForeignKeyConstraint(['agency_id', 'brief_id'], ['briefs.agency_id', 'briefs.id']),
        ForeignKeyConstraint(['agency_id', 'manifest_id'], ['fixture_manifests.agency_id', 'fixture_manifests.id']),
        Index('brief_history', 'agency_id', 'brief_id', text('revision DESC')).ddl_if(dialect="postgresql"),
    )


class DeliveryTask(Base):
    __tablename__ = 'delivery_tasks'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    demo_run_id = Column(GUID, nullable=False)
    brief_id = Column(GUID, nullable=False)
    state = Column(Text, default='brief_captured', nullable=False)
    current_delivery_id = Column(GUID, nullable=True)
    current_bundle_id = Column(GUID, nullable=True)
    review_required = Column(Boolean, default=False, server_default=text('false'), nullable=False)
    hold_reasons = Column(UniversalJSON, default=list, server_default=text("'[]'"), nullable=False)
    version = Column(BigInteger, default=1, server_default=text('1'), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("state IN ('brief_captured','checks_approved','awaiting_delivery',\n    'verifying','correction_requested','evidence_passed','payment_initiated','reconciling',\n    'paid','failed','unclaimed','cancelled')"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'brief_id']),
        ForeignKeyConstraint(['agency_id', 'demo_run_id'], ['demo_runs.agency_id', 'demo_runs.id']),
        ForeignKeyConstraint(['agency_id', 'brief_id'], ['briefs.agency_id', 'briefs.id']),
        ForeignKeyConstraint(['agency_id', 'id', 'current_delivery_id'], ['deliveries.agency_id', 'deliveries.task_id', 'deliveries.id'], name='task_current_delivery_fk', use_alter=True),
        ForeignKeyConstraint(['agency_id', 'id', 'current_bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.task_id', 'evidence_bundles.id'], name='task_current_bundle_fk', use_alter=True),
        Index('task_queue', 'agency_id', 'demo_run_id', 'state', text('updated_at DESC'), 'id').ddl_if(dialect="postgresql"),
    )


class Mandate(Base):
    __tablename__ = 'mandates'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    current_version_id = Column(GUID, nullable=True)
    __table_args__ = (
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id'], ['delivery_tasks.agency_id', 'delivery_tasks.id']),
        ForeignKeyConstraint(['agency_id', 'id', 'current_version_id'], ['mandate_versions.agency_id', 'mandate_versions.mandate_id', 'mandate_versions.id'], name='mandate_current_version_fk', use_alter=True),
    )


class OutboxEvent(Base):
    __tablename__ = 'outbox_events'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=True)
    event_type = Column(Text, nullable=False)
    dedup_key = Column(Text, nullable=False)
    payload = Column(UniversalJSON, nullable=False)
    stage_state = Column(UniversalJSON, default=dict, server_default=text("'{}'"), nullable=False)
    state = Column(Text, default='ready', nullable=False)
    available_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    lease_token = Column(GUID, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, default=0, server_default=text('0'), nullable=False)
    last_error_code = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("(state='leased' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) OR (state<>'leased' AND lease_token IS NULL AND lease_until IS NULL)", name='outbox_lease_check'),
        CheckConstraint("jsonb_typeof(payload)='object' AND jsonb_typeof(stage_state)='object'", name='outbox_json_check').ddl_if(dialect="postgresql"),
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        CheckConstraint("state IN ('ready','leased','done','failed','held')"),
        CheckConstraint('attempt_count >= 0'),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'dedup_key']),
        ForeignKeyConstraint(['agency_id', 'task_id'], ['delivery_tasks.agency_id', 'delivery_tasks.id']),
        Index('outbox_ready', 'available_at', 'id', postgresql_where=text("state='ready'")).ddl_if(dialect="postgresql"),
        Index('outbox_expired', 'lease_until', 'id', postgresql_where=text("state='leased'")).ddl_if(dialect="postgresql"),
    )


class AIInteraction(Base):
    __tablename__ = 'ai_interactions'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    job_id = Column(GUID, nullable=False)
    stage = Column(Text, nullable=False)
    brief_revision_id = Column(GUID, nullable=True)
    bundle_id = Column(GUID, nullable=True)
    model_ref = Column(Text, nullable=False)
    prompt_version = Column(Text, nullable=False)
    schema_version = Column(Text, nullable=False)
    input_digest = Column(Text, nullable=False)
    input_refs = Column(UniversalJSON, nullable=False)
    output = Column(UniversalJSON, nullable=True)
    output_digest = Column(Text, nullable=True)
    validated = Column(Boolean, default=False, nullable=False)
    error_code = Column(Text, nullable=True)
    usage = Column(UniversalJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("stage IN ('compiler','reviewer')"),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'job_id'], ['outbox_events.agency_id', 'outbox_events.id']),
        ForeignKeyConstraint(['agency_id', 'brief_revision_id'], ['brief_revisions.agency_id', 'brief_revisions.id']),
        ForeignKeyConstraint(['agency_id', 'bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.id'], name='interaction_bundle_fk', use_alter=True),
        Index('ai_by_job', 'agency_id', 'job_id', 'created_at').ddl_if(dialect="postgresql"),
    )


class Compilation(Base):
    __tablename__ = 'compilations'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    brief_revision_id = Column(GUID, nullable=False)
    job_id = Column(GUID, nullable=False)
    status = Column(Text, default='queued', nullable=False)
    interaction_id = Column(GUID, nullable=True)
    proposal = Column(UniversalJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','ready','ambiguous','failed','stale')"),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'brief_revision_id'], ['brief_revisions.agency_id', 'brief_revisions.id']),
        ForeignKeyConstraint(['agency_id', 'job_id'], ['outbox_events.agency_id', 'outbox_events.id']),
        ForeignKeyConstraint(['agency_id', 'interaction_id'], ['ai_interactions.agency_id', 'ai_interactions.id']),
    )


class MandateVersion(Base):
    __tablename__ = 'mandate_versions'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    mandate_id = Column(GUID, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    brief_revision_id = Column(GUID, nullable=False)
    compilation_id = Column(GUID, nullable=False)
    contractor_id = Column(GUID, nullable=False)
    recipient_binding_id = Column(GUID, nullable=False)
    lifecycle_state = Column(Text, default='draft', nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    principal_cap_cents = Column(BigInteger, nullable=False)
    currency = Column(Text, default='USD', nullable=False)
    max_attempts = Column(SmallInteger, default=3, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    public_payload = Column(UniversalJSON, nullable=False)
    payload_digest = Column(Text, nullable=False)
    approved_by = Column(GUID, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint('version > 0'),
        CheckConstraint("lifecycle_state IN ('draft','approved','expired','superseded','exhausted')"),
        CheckConstraint('amount_cents > 0'),
        CheckConstraint('principal_cap_cents >= amount_cents'),
        CheckConstraint("currency='USD'"),
        CheckConstraint('max_attempts BETWEEN 1 AND 3'),
        CheckConstraint("payload_digest ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        UniqueConstraint(*['agency_id', 'mandate_id', 'id']),
        UniqueConstraint(*['agency_id', 'mandate_id', 'version']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_id'], ['mandates.agency_id', 'mandates.task_id', 'mandates.id']),
        ForeignKeyConstraint(['agency_id', 'brief_revision_id'], ['brief_revisions.agency_id', 'brief_revisions.id']),
        ForeignKeyConstraint(['agency_id', 'compilation_id'], ['compilations.agency_id', 'compilations.id']),
        ForeignKeyConstraint(['agency_id', 'contractor_id', 'recipient_binding_id'], ['recipient_bindings.agency_id', 'recipient_bindings.contractor_id', 'recipient_bindings.id']),
        ForeignKeyConstraint(['agency_id', 'approved_by'], ['users.agency_id', 'users.id']),
        CheckConstraint("(approved_at IS NULL AND approved_by IS NULL AND lifecycle_state='draft') OR\n  (approved_at IS NOT NULL AND approved_by IS NOT NULL AND lifecycle_state<>'draft')", name='approval_identity_check'),
        Index('one_current_approved_version', 'agency_id', 'mandate_id', unique=True, postgresql_where=text("lifecycle_state='approved'")).ddl_if(dialect="postgresql"),
        Index('mandate_history', 'agency_id', 'mandate_id', text('version DESC')).ddl_if(dialect="postgresql"),
    )


class AcceptanceCheck(Base):
    __tablename__ = 'acceptance_checks'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    check_id = Column(Text, nullable=False)
    template_type = Column(Text, nullable=False)
    params = Column(UniversalJSON, nullable=False)
    compiled_by = Column(Text, default='ai', nullable=False)
    approved = Column(Boolean, default=False, server_default=text('false'), nullable=False)
    __table_args__ = (
        CheckConstraint("check_id IN ('C01','C02','C03')"),
        CheckConstraint("template_type IN ('viewport_no_horizontal_overflow',\n    'cart_total_unchanged','keyboard_checkout_reachable','api_status','api_schema',\n    'api_total_matches_fixture','keyboard_activation','accessible_control_name')"),
        CheckConstraint("jsonb_typeof(params)='object'").ddl_if(dialect="postgresql"),
        CheckConstraint("compiled_by='ai'"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'mandate_version_id', 'id']),
        UniqueConstraint(*['agency_id', 'mandate_version_id', 'check_id']),
        UniqueConstraint(*['agency_id', 'mandate_version_id', 'template_type']),
        ForeignKeyConstraint(['agency_id', 'mandate_version_id'], ['mandate_versions.agency_id', 'mandate_versions.id']),
    )


class Delivery(Base):
    __tablename__ = 'deliveries'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    artifact_version_id = Column(GUID, nullable=False)
    artifact_digest = Column(Text, nullable=False)
    mandate_digest = Column(Text, nullable=False)
    submitted_by = Column(GUID, nullable=False)
    claim = Column(Text, nullable=False)
    claim_digest = Column(Text, nullable=False)
    sequence = Column(Integer, default=1, nullable=False)
    previous_delivery_id = Column(GUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint('length(claim) BETWEEN 1 AND 4000'),
        CheckConstraint('sequence > 0'),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'mandate_version_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'sequence']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_version_id'], ['mandate_versions.agency_id', 'mandate_versions.task_id', 'mandate_versions.id']),
        ForeignKeyConstraint(['agency_id', 'artifact_version_id'], ['artifact_versions.agency_id', 'artifact_versions.id']),
        ForeignKeyConstraint(['agency_id', 'submitted_by'], ['users.agency_id', 'users.id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'previous_delivery_id'], ['deliveries.agency_id', 'deliveries.task_id', 'deliveries.id'], name='delivery_predecessor_fk', use_alter=True),
        Index('delivery_history', 'agency_id', 'task_id', text('sequence DESC')).ddl_if(dialect="postgresql"),
    )


class VerificationJob(Base):
    __tablename__ = 'verification_jobs'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    delivery_id = Column(GUID, nullable=False)
    state = Column(Text, default='queued', nullable=False)
    inputs = Column(UniversalJSON, nullable=False)
    input_digest = Column(Text, nullable=False)
    worker_id = Column(Text, nullable=True)
    lease_token = Column(GUID, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    lease_attempt = Column(Integer, default=0, server_default=text('0'), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completion_digest = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("state IN ('queued','running','completed','error','stale')"),
        CheckConstraint("completion_digest IS NULL OR completion_digest ~ '^[0-9a-f]{64}$'", name="verification_completion_digest").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'delivery_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'delivery_id'], ['deliveries.agency_id', 'deliveries.task_id', 'deliveries.id']),
        Index('verification_claim', 'state', 'lease_until', 'created_at', postgresql_where=text("state IN ('queued','running')")).ddl_if(dialect="postgresql"),
    )


class EvidenceBundle(Base):
    __tablename__ = 'evidence_bundles'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    delivery_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    verification_job_id = Column(GUID, nullable=False)
    artifact_digest = Column(Text, nullable=False)
    mandate_digest = Column(Text, nullable=False)
    bundle_digest = Column(Text, nullable=False)
    manifest_id = Column(GUID, nullable=False)
    manifest_json = Column(UniversalJSON, nullable=False, default=dict, server_default=text("'{}'"))
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        UniqueConstraint(*['agency_id', 'mandate_version_id', 'id']),
        UniqueConstraint(*['agency_id', 'verification_job_id']),
        UniqueConstraint(*['agency_id', 'task_id', 'mandate_version_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_version_id', 'delivery_id'], ['deliveries.agency_id', 'deliveries.task_id', 'deliveries.mandate_version_id', 'deliveries.id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'delivery_id', 'verification_job_id'], ['verification_jobs.agency_id', 'verification_jobs.task_id', 'verification_jobs.delivery_id', 'verification_jobs.id']),
        ForeignKeyConstraint(['agency_id', 'manifest_id'], ['fixture_manifests.agency_id', 'fixture_manifests.id']),
        Index('evidence_history', 'agency_id', 'task_id', text('created_at DESC')).ddl_if(dialect="postgresql"),
    )


class EvidenceResult(Base):
    __tablename__ = 'evidence_results'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    acceptance_check_id = Column(GUID, nullable=False)
    outcome = Column(Text, nullable=False)
    observations = Column(UniversalJSON, nullable=False)
    result_digest = Column(Text, nullable=False)
    completed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (
        CheckConstraint("outcome IN ('pass','fail','error')"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'bundle_id', 'acceptance_check_id']),
        ForeignKeyConstraint(['agency_id', 'mandate_version_id', 'bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.mandate_version_id', 'evidence_bundles.id']),
        ForeignKeyConstraint(['agency_id', 'mandate_version_id', 'acceptance_check_id'], ['acceptance_checks.agency_id', 'acceptance_checks.mandate_version_id', 'acceptance_checks.id']),
        CheckConstraint('octet_length(observations::text) <= 65536', name='result_size_check').ddl_if(dialect="postgresql"),
    )


class EvidenceArtifact(Base):
    __tablename__ = 'evidence_artifacts'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    check_id = Column(Text, nullable=True)
    media_type = Column(Text, nullable=False)
    digest = Column(Text, nullable=False)
    content = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("check_id IN ('C01','C02','C03')"),
        CheckConstraint("media_type IN ('image/png','application/json')"),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.id']),
        CheckConstraint("octet_length(content) <= CASE WHEN media_type='image/png' THEN 524288 ELSE 65536 END", name='artifact_size_check').ddl_if(dialect="postgresql"),
        Index('evidence_bytes', 'agency_id', 'bundle_id', 'check_id').ddl_if(dialect="postgresql"),
    )


class Correction(Base):
    __tablename__ = 'corrections'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    delivery_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    review_interaction_id = Column(GUID, nullable=False)
    contractor_message = Column(Text, nullable=False)
    evidence_refs = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint('length(contractor_message) BETWEEN 1 AND 2000'),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'delivery_id'], ['deliveries.agency_id', 'deliveries.task_id', 'deliveries.id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.task_id', 'evidence_bundles.id']),
        ForeignKeyConstraint(['agency_id', 'review_interaction_id'], ['ai_interactions.agency_id', 'ai_interactions.id']),
        Index('corrections_by_task', 'agency_id', 'task_id', 'created_at').ddl_if(dialect="postgresql"),
    )


class ReviewResolution(Base):
    __tablename__ = 'review_resolutions'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    review_interaction_id = Column(GUID, nullable=False)
    resolved_by = Column(GUID, nullable=False)
    rationale = Column(Text, nullable=False)
    evidence_refs = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint('length(rationale) BETWEEN 1 AND 1000'),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.task_id', 'evidence_bundles.id']),
        ForeignKeyConstraint(['agency_id', 'review_interaction_id'], ['ai_interactions.agency_id', 'ai_interactions.id']),
        ForeignKeyConstraint(['agency_id', 'resolved_by'], ['users.agency_id', 'users.id']),
    )


class DecisionRequest(Base):
    __tablename__ = 'decision_requests'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    bundle_id = Column(GUID, nullable=False)
    source = Column(Text, default='ai', nullable=False)
    review_interaction_id = Column(GUID, nullable=False)
    state = Column(Text, default='queued', nullable=False)
    evaluation_generation = Column(Integer, default=1, server_default=text('1'), nullable=False)
    request_digest = Column(Text, nullable=False)
    evidence_refs = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("source IN ('ai','owner_resolution','owner_reevaluation')"),
        CheckConstraint("state IN ('queued','held','deduplicated')"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'mandate_version_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_version_id'], ['mandate_versions.agency_id', 'mandate_versions.task_id', 'mandate_versions.id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_version_id', 'bundle_id'], ['evidence_bundles.agency_id', 'evidence_bundles.task_id', 'evidence_bundles.mandate_version_id', 'evidence_bundles.id']),
        ForeignKeyConstraint(['agency_id', 'review_interaction_id'], ['ai_interactions.agency_id', 'ai_interactions.id']),
        Index('release_history', 'agency_id', 'task_id', 'created_at').ddl_if(dialect="postgresql"),
    )


class PaymentObligation(Base):
    __tablename__ = 'payment_obligations'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    currency = Column(Text, default='USD', nullable=False)
    next_attempt_no = Column(SmallInteger, server_default=text('1'), nullable=False)
    # Omit executor-owned values from API inserts, including the implicit NULL pointer.
    success_attempt_id = Column(GUID, server_default=FetchedValue(), nullable=True)
    reserved_cents = Column(BigInteger, server_default=text('0'), nullable=False)
    consumed_cents = Column(BigInteger, server_default=text('0'), nullable=False)
    __table_args__ = (
        CheckConstraint("currency='USD'"),
        CheckConstraint('next_attempt_no BETWEEN 1 AND 4'),
        CheckConstraint('reserved_cents >= 0'),
        CheckConstraint('consumed_cents >= 0'),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'task_id'], ['delivery_tasks.agency_id', 'delivery_tasks.id']),
        ForeignKeyConstraint(['agency_id', 'id', 'success_attempt_id'], ['payment_attempts.agency_id', 'payment_attempts.obligation_id', 'payment_attempts.id'], name='obligation_success_attempt_fk', use_alter=True),
    )


class PaymentAttempt(Base):
    __tablename__ = 'payment_attempts'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    task_id = Column(GUID, nullable=False)
    obligation_id = Column(GUID, nullable=False)
    mandate_version_id = Column(GUID, nullable=False)
    decision_request_id = Column(GUID, nullable=False)
    attempt_no = Column(SmallInteger, nullable=False)
    principal_cents = Column(BigInteger, nullable=False)
    currency = Column(Text, default='USD', nullable=False)
    sender_batch_id = Column(String(256), nullable=False)
    sender_item_id = Column(String(63), nullable=False)
    request_ciphertext = deferred(Column(LargeBinary, nullable=False))
    request_digest = Column(Text, nullable=False)
    state = Column(Text, default='prepared', nullable=False)
    unresolved = Column(Boolean, default=True, server_default=text('true'), nullable=False)
    nonpayment_confirmed = Column(Boolean, default=False, server_default=text('false'), nullable=False)
    successful = Column(Boolean, default=False, server_default=text('false'), nullable=False)
    first_dispatch_at = Column(DateTime(timezone=True), nullable=True)
    retransmission_cutoff = Column(DateTime(timezone=True), nullable=True)
    transmission_count = Column(Integer, default=0, server_default=text('0'), nullable=False)
    guard_snapshot = Column(UniversalJSON, nullable=False)
    last_reconciled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint('attempt_no BETWEEN 1 AND 3'),
        CheckConstraint('principal_cents > 0'),
        CheckConstraint("currency='USD'"),
        UniqueConstraint('sender_batch_id'),
        UniqueConstraint('sender_item_id'),
        CheckConstraint("request_digest ~ '^[0-9a-f]{64}$'").ddl_if(dialect="postgresql"),
        CheckConstraint("state IN ('prepared','dispatching','unknown','processing',\n    'unclaimed','success','failed','cancelled','blocked')"),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'obligation_id', 'id']),
        UniqueConstraint(*['agency_id', 'task_id', 'id']),
        UniqueConstraint(*['agency_id', 'obligation_id', 'attempt_no']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'obligation_id'], ['payment_obligations.agency_id', 'payment_obligations.task_id', 'payment_obligations.id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_version_id'], ['mandate_versions.agency_id', 'mandate_versions.task_id', 'mandate_versions.id']),
        ForeignKeyConstraint(['agency_id', 'task_id', 'mandate_version_id', 'decision_request_id'], ['decision_requests.agency_id', 'decision_requests.task_id', 'decision_requests.mandate_version_id', 'decision_requests.id']),
        CheckConstraint('unresolved OR successful OR nonpayment_confirmed', name='attempt_resolution_check'),
        CheckConstraint('NOT (successful AND unresolved)', name='attempt_success_resolved_check'),
        CheckConstraint('NOT (successful AND nonpayment_confirmed)', name='attempt_disposition_check'),
        CheckConstraint("(state='success' AND successful) OR (state<>'success' AND NOT successful)", name='attempt_state_check'),
        Index('one_unresolved_attempt', 'agency_id', 'obligation_id', unique=True, postgresql_where=text('unresolved')).ddl_if(dialect="postgresql"),
        Index('one_successful_attempt', 'agency_id', 'obligation_id', unique=True, postgresql_where=text('successful')).ddl_if(dialect="postgresql"),
        Index('active_payments', 'agency_id', 'last_reconciled_at', 'created_at', postgresql_where=text('unresolved')).ddl_if(dialect="postgresql"),
        Index('attempts_by_task', 'agency_id', 'task_id', 'attempt_no').ddl_if(dialect="postgresql"),
    )


class PayoutItem(Base):
    __tablename__ = 'payout_items'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    attempt_id = Column(GUID, nullable=False)
    payer_account_ref = Column(Text, default='payer_sandbox_us', nullable=False)
    provider_batch_id = Column(Text, nullable=True)
    provider_item_id = Column(Text, nullable=True)
    provider_transaction_id = Column(Text, nullable=True)
    raw_status = Column(Text, nullable=True)
    canonical_state = Column(Text, default='created', nullable=False)
    fee_cents = Column(BigInteger, nullable=True)
    fee_currency = Column(Text, nullable=True)
    binding_verified = Column(Boolean, default=False, server_default=text('false'), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("payer_account_ref='payer_sandbox_us'"),
        CheckConstraint("canonical_state IN ('created','processing','success',\n    'unclaimed','cancelled','failed','blocked')"),
        CheckConstraint('fee_cents >= 0'),
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'attempt_id']),
        ForeignKeyConstraint(['agency_id', 'attempt_id'], ['payment_attempts.agency_id', 'payment_attempts.id']),
        CheckConstraint("canonical_state<>'success' OR (provider_item_id IS NOT NULL AND raw_status='SUCCESS' AND binding_verified)", name='matched_item_success_check'),
        Index('provider_item_once', 'payer_account_ref', 'provider_item_id', unique=True, postgresql_where=text('provider_item_id IS NOT NULL')).ddl_if(dialect="postgresql"),
    )


class ProviderObservation(Base):
    __tablename__ = 'provider_observations'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    attempt_id = Column(GUID, nullable=False)
    operation = Column(Text, nullable=False)
    observed_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    raw_status = Column(Text, nullable=True)
    response_digest = Column(Text, nullable=False)
    redacted_response = Column(UniversalJSON, nullable=False)
    protected_response_ciphertext = deferred(Column(LargeBinary, nullable=True))
    binding_verified = Column(Boolean, default=False, nullable=False)
    __table_args__ = (
        UniqueConstraint(*['agency_id', 'id']),
        UniqueConstraint(*['agency_id', 'attempt_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'attempt_id'], ['payment_attempts.agency_id', 'payment_attempts.id']),
        Index('provider_history', 'agency_id', 'attempt_id', 'observed_at', 'id').ddl_if(dialect="postgresql"),
    )


class BudgetEntry(Base):
    __tablename__ = 'budget_entries'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    obligation_id = Column(GUID, nullable=False)
    attempt_id = Column(GUID, nullable=False)
    phase = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    principal_cents = Column(BigInteger, nullable=False)
    reserved_delta = Column(BigInteger, nullable=False)
    consumed_delta = Column(BigInteger, nullable=False)
    proof_observation_id = Column(GUID, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("phase IN ('reservation','disposition')"),
        CheckConstraint("kind IN ('reserve','consume','release')"),
        CheckConstraint('principal_cents > 0'),
        UniqueConstraint(*['agency_id', 'attempt_id', 'phase']),
        ForeignKeyConstraint(['agency_id', 'obligation_id', 'attempt_id'], ['payment_attempts.agency_id', 'payment_attempts.obligation_id', 'payment_attempts.id']),
        ForeignKeyConstraint(['agency_id', 'attempt_id', 'proof_observation_id'], ['provider_observations.agency_id', 'provider_observations.attempt_id', 'provider_observations.id'], name='ledger_proof_fk', use_alter=True),
        CheckConstraint("(phase='reservation' AND kind='reserve' AND reserved_delta=principal_cents AND consumed_delta=0) OR\n  (phase='disposition' AND kind='consume' AND reserved_delta=-principal_cents AND consumed_delta=principal_cents) OR\n  (phase='disposition' AND kind='release' AND reserved_delta=-principal_cents AND consumed_delta=0)", name='ledger_delta_check'),
        Index('ledger_by_obligation', 'agency_id', 'obligation_id', 'created_at', 'id').ddl_if(dialect="postgresql"),
    )


class WebhookDelivery(Base):
    __tablename__ = 'webhook_deliveries'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    claimed_event_id = Column(Text, nullable=False)
    transmission_id = Column(Text, nullable=False)
    raw_body = Column(LargeBinary, nullable=False)
    payload_digest = Column(Text, nullable=False)
    headers = Column(UniversalJSON, nullable=False)
    verification_state = Column(Text, nullable=False)
    verification_result = Column(UniversalJSON, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        CheckConstraint('octet_length(raw_body) <= 65536').ddl_if(dialect="postgresql"),
        CheckConstraint("verification_state IN ('pending','verified','invalid','error')"),
        UniqueConstraint(*['agency_id', 'id']),
        Index('quarantine_pending', 'received_at', 'id', postgresql_where=text("verification_state IN ('pending','error')")).ddl_if(dialect="postgresql"),
        Index('quarantine_claimed_id', 'agency_id', 'claimed_event_id').ddl_if(dialect="postgresql"),
    )


class WebhookEvent(Base):
    __tablename__ = 'webhook_events'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    payer_account_ref = Column(Text, default='payer_sandbox_us', nullable=False)
    provider_event_id = Column(Text, nullable=False)
    delivery_id = Column(GUID, nullable=False)
    payload_digest = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=False)
    matched_attempt_id = Column(GUID, nullable=True)
    __table_args__ = (
        CheckConstraint("payer_account_ref='payer_sandbox_us'"),
        UniqueConstraint(*['payer_account_ref', 'provider_event_id']),
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'delivery_id'], ['webhook_deliveries.agency_id', 'webhook_deliveries.id']),
        ForeignKeyConstraint(['agency_id', 'matched_attempt_id'], ['payment_attempts.agency_id', 'payment_attempts.id']),
    )


class CommandReceipt(Base):
    __tablename__ = 'command_receipts'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    principal_user_id = Column(GUID, nullable=False)
    effective_user_id = Column(GUID, nullable=False)
    operation = Column(Text, nullable=False)
    idempotency_key = Column(GUID, nullable=False)
    request_digest = Column(Text, nullable=False)
    http_status = Column(Integer, nullable=False)
    response = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        UniqueConstraint(*['agency_id', 'principal_user_id', 'effective_user_id', 'operation', 'idempotency_key']),
        ForeignKeyConstraint(['agency_id', 'principal_user_id'], ['users.agency_id', 'users.id']),
        ForeignKeyConstraint(['agency_id', 'effective_user_id'], ['users.agency_id', 'users.id']),
    )


class ToolInvocation(Base):
    __tablename__ = 'tool_invocations'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    job_id = Column(GUID, nullable=False)
    tool_name = Column(Text, nullable=False)
    input_digest = Column(Text, nullable=False)
    state = Column(Text, nullable=False)
    interaction_id = Column(GUID, nullable=True)
    result = Column(UniversalJSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        CheckConstraint("tool_name IN ('propose_checks','inspect_evidence','request_correction','request_payout')"),
        CheckConstraint("state IN ('running','done','failed','stale')"),
        UniqueConstraint(*['agency_id', 'job_id', 'tool_name', 'input_digest']),
        ForeignKeyConstraint(['agency_id', 'job_id'], ['outbox_events.agency_id', 'outbox_events.id']),
        ForeignKeyConstraint(['agency_id', 'interaction_id'], ['ai_interactions.agency_id', 'ai_interactions.id'], name='tool_interaction_fk', use_alter=True),
    )


class DemoArchive(Base):
    __tablename__ = 'demo_archives'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    agency_id = Column(GUID, nullable=False)
    completed_task_id = Column(GUID, nullable=False)
    bundle_digest = Column(Text, nullable=False)
    archived_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        UniqueConstraint(*['agency_id', 'id']),
        ForeignKeyConstraint(['agency_id', 'completed_task_id'], ['delivery_tasks.agency_id', 'delivery_tasks.id'], name='archive_task_fk', use_alter=True),
    )


class AuditLog(Base):
    __tablename__ = 'audit_log'
    id = Column(GUID, primary_key=True, default=uuid.uuid4, nullable=False)
    sequence = Column(BigInteger, Identity(always=True), nullable=False)
    agency_id = Column(GUID, nullable=False)
    principal_user_id = Column(GUID, nullable=True)
    effective_user_id = Column(GUID, nullable=True)
    service_actor = Column(Text, nullable=True)
    event_type = Column(Text, nullable=False)
    correlation_id = Column(GUID, nullable=False)
    references_json = Column(UniversalJSON, nullable=False)
    details = Column(UniversalJSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, server_default=text('CURRENT_TIMESTAMP'), nullable=False)
    __table_args__ = (
        UniqueConstraint('sequence'),
        ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        ForeignKeyConstraint(['agency_id', 'principal_user_id'], ['users.agency_id', 'users.id']),
        ForeignKeyConstraint(['agency_id', 'effective_user_id'], ['users.agency_id', 'users.id']),
        CheckConstraint('principal_user_id IS NOT NULL OR service_actor IS NOT NULL', name='audit_actor_check'),
        Index('audit_by_task_refs', 'references_json', postgresql_using='gin').ddl_if(dialect="postgresql"),
        Index('audit_timeline', 'agency_id', 'created_at', 'sequence').ddl_if(dialect="postgresql"),
    )
