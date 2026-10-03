"""Actual PostgreSQL fixtures; business/provider bytes below are explicit test doubles."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from backend.app import models as m
from fixture_contract.registry import load_contract
from backend.migrate import upgrade_database
from backend.provision_db import provision_roles

PASSWORDS = {
    "proofpay_migrator": "test_migration_only",
    "proofpay_api": "test_api_only",
    "proofpay_executor": "test_executor_only",
}
DIGEST = "a" * 64
TRUSTED_CONTRACT = load_contract()


@pytest.fixture(scope="session")
def database_factory():
    admin_url = os.environ.get("PROOFPAY_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("Set PROOFPAY_TEST_DATABASE_URL to an isolated PostgreSQL server for acceptance.")
    admin = create_engine(make_url(admin_url).set(drivername="postgresql+psycopg"), poolclass=NullPool)
    databases = []

    def create(migrate=True):
        name = "proofpay_test_" + uuid.uuid4().hex
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        databases.append(name)
        database_url = make_url(admin_url).set(database=name)
        provision_roles(database_url.render_as_string(hide_password=False), PASSWORDS)
        url = database_url.set(username="proofpay_migrator", password=PASSWORDS["proofpay_migrator"], drivername="postgresql+psycopg")
        if migrate:
            upgrade_database(url)
        return url

    try:
        yield create
    finally:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            for name in databases:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()


@pytest.fixture(scope="session")
def postgres_url(database_factory):
    return database_factory()


@pytest.fixture
def pg_engine(postgres_url):
    engine = create_engine(postgres_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def graph(pg_engine):
    """A complete relational chain, with no real model, browser or payout claims."""
    ids = {}

    def insert(connection, model, key, **values):
        identifier = uuid.uuid4()
        values = {"id": identifier, **values}
        if key != "agency":
            values.setdefault("agency_id", ids["agency"])
        connection.execute(model.__table__.insert().values(**values))
        ids[key] = identifier
        return identifier

    with pg_engine.begin() as c:
        insert(c, m.Agency, "agency", name="PostgreSQL acceptance double", advisory_lock_key=uuid.uuid4().int % (2**62), principal_limit_cents=10000)
        insert(c, m.User, "owner", role="owner", display_name="Test owner")
        insert(c, m.Contractor, "contractor", user_id=ids["owner"], recipient_ref="contractor_maya", display_name="Test recipient")
        insert(c, m.RecipientBinding, "binding", contractor_id=ids["contractor"], receiver_ciphertext=b"test-only-ciphertext", receiver_hash=DIGEST, key_version="test")
        insert(c, m.DemoRun, "run", state="active")
        insert(c, m.FixtureManifest, "manifest", digest=TRUSTED_CONTRACT.digest, manifest=TRUSTED_CONTRACT.model_dump(mode="json"))
        insert(c, m.ArtifactVersion, "artifact", manifest_id=ids["manifest"], artifact_ref="test-artifact", family="responsive_css", digest=DIGEST, relative_path="/test")
        insert(c, m.Brief, "brief", created_by=ids["owner"])
        insert(c, m.BriefRevision, "revision", brief_id=ids["brief"], title="Test", body="Test relational integrity", family="responsive_css", manifest_id=ids["manifest"], proposed_terms={}, digest=DIGEST)
        insert(c, m.DeliveryTask, "task", demo_run_id=ids["run"], brief_id=ids["brief"])
        insert(c, m.OutboxEvent, "job", task_id=ids["task"], event_type="test_only", dedup_key="test", payload={})
        insert(c, m.Compilation, "compilation", brief_revision_id=ids["revision"], job_id=ids["job"])
        insert(c, m.Mandate, "mandate", task_id=ids["task"])
        insert(c, m.MandateVersion, "version", task_id=ids["task"], mandate_id=ids["mandate"], brief_revision_id=ids["revision"], compilation_id=ids["compilation"], contractor_id=ids["contractor"], recipient_binding_id=ids["binding"], amount_cents=100, principal_cap_cents=300, expires_at=datetime.now(timezone.utc)+timedelta(days=1), public_payload={"test_double": True}, payload_digest=DIGEST)
        for number, template in enumerate(("viewport_no_horizontal_overflow", "cart_total_unchanged", "keyboard_checkout_reachable"), start=1):
            insert(c, m.AcceptanceCheck, f"check{number}", mandate_version_id=ids["version"], check_id=f"C0{number}", template_type=template, params={}, approved=True)
        c.execute(m.MandateVersion.__table__.update().where(m.MandateVersion.id==ids["version"]).values(lifecycle_state="approved", approved_by=ids["owner"], approved_at=datetime.now(timezone.utc)))
        insert(c, m.Delivery, "delivery", task_id=ids["task"], mandate_version_id=ids["version"], artifact_version_id=ids["artifact"], artifact_digest=DIGEST, mandate_digest=DIGEST, submitted_by=ids["owner"], claim="Test double", claim_digest=DIGEST)
        insert(c, m.VerificationJob, "verification", task_id=ids["task"], delivery_id=ids["delivery"], inputs={}, input_digest=DIGEST)
        insert(c, m.EvidenceBundle, "bundle", task_id=ids["task"], delivery_id=ids["delivery"], mandate_version_id=ids["version"], verification_job_id=ids["verification"], artifact_digest=DIGEST, mandate_digest=DIGEST, bundle_digest=DIGEST, manifest_id=ids["manifest"])
        insert(c, m.AIInteraction, "review", job_id=ids["job"], stage="reviewer", bundle_id=ids["bundle"], model_ref="test-double", prompt_version="test", schema_version="test", input_digest=DIGEST, input_refs=[])
        insert(c, m.DecisionRequest, "decision", task_id=ids["task"], mandate_version_id=ids["version"], bundle_id=ids["bundle"], review_interaction_id=ids["review"], request_digest=DIGEST, evidence_refs=[])
        insert(c, m.PaymentObligation, "obligation", task_id=ids["task"])
        insert(c, m.PaymentAttempt, "attempt", **attempt_values(ids))
        insert(c, m.PayoutItem, "item", attempt_id=ids["attempt"])
    return ids


def attempt_values(graph, number=1):
    return dict(agency_id=graph["agency"], task_id=graph["task"], obligation_id=graph["obligation"],
                mandate_version_id=graph["version"], decision_request_id=graph["decision"], attempt_no=number,
                principal_cents=100, sender_batch_id="test-batch-"+uuid.uuid4().hex,
                sender_item_id="test-item-"+uuid.uuid4().hex, request_ciphertext=b"test-payload",
                request_digest=DIGEST, guard_snapshot={"test_double": True})
