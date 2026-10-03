"""Database acceptance uses PostgreSQL, with explicitly simulated business/provider inputs."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from backend.app import models as m
from backend.app.database import Base
from backend.migrate import HEAD_REVISION, MIGRATIONS, alembic_config, upgrade_database
from backend.tests.postgres_support import (
    DIGEST, PASSWORDS, attempt_values, database_factory, graph, pg_engine, postgres_url,
)

pytestmark = pytest.mark.postgres


def rejection(engine, statement, state="23514", params=None):
    with engine.begin() as connection:
        with pytest.raises(DBAPIError) as error:
            with connection.begin_nested():
                connection.execute(statement, params or {})
        assert error.value.orig.sqlstate == state


def test_migrated_schema_matches_all_36_orm_tables(pg_engine):
    with pg_engine.connect() as c:
        assert len(Base.metadata.tables) == 36
        assert set(inspect(c).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        context = MigrationContext.configure(c, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == HEAD_REVISION


def test_upgrade_is_repeatable_and_preserves_financial_history(postgres_url, pg_engine, graph):
    upgrade_database(postgres_url)
    with pg_engine.connect() as c:
        assert c.scalar(select(m.PaymentAttempt.id).where(m.PaymentAttempt.id==graph["attempt"])) == graph["attempt"]
        assert c.scalar(select(m.PaymentObligation.id).where(m.PaymentObligation.id==graph["obligation"])) == graph["obligation"]


def test_upgrade_from_versioned_baseline_preserves_base_identities_and_balances(database_factory):
    url = database_factory(migrate=False)
    engine = create_engine(url)
    agency = uuid.uuid4()
    owner = uuid.uuid4()
    run = uuid.uuid4()
    with engine.begin() as c:
        command.upgrade(alembic_config(c), "0001_runtime_baseline")
        c.execute(m.Agency.__table__.insert().values(id=agency, name="Retained", advisory_lock_key=88, principal_limit_cents=500, consumed_cents=100))
        c.execute(m.User.__table__.insert().values(id=owner, agency_id=agency, role="owner", display_name="Retained owner"))
        c.execute(m.DemoRun.__table__.insert().values(id=run, agency_id=agency, state="active"))
        c.execute(m.Agency.__table__.update().where(m.Agency.id==agency).values(current_demo_run_id=run))
    upgrade_database(url)
    with engine.connect() as c:
        assert c.scalar(select(m.Agency.consumed_cents).where(m.Agency.id==agency)) == 100
        assert c.scalar(select(m.Agency.current_demo_run_id).where(m.Agency.id==agency)) == run
        assert c.scalar(select(m.User.id).where(m.User.id==owner)) == owner
    engine.dispose()


def test_adopt_exact_unversioned_runtime_schema(database_factory):
    url = database_factory(migrate=False)
    engine = create_engine(url)
    agency = uuid.uuid4()
    with engine.begin() as c:
        c.exec_driver_sql((MIGRATIONS/"versions/0001_runtime_baseline.sql").read_text())
        c.execute(m.Agency.__table__.insert().values(id=agency, name="Legacy", advisory_lock_key=99, principal_limit_cents=500, consumed_cents=100))
    with pytest.raises(RuntimeError, match="unversioned"):
        upgrade_database(url)
    upgrade_database(url, adopt=True)
    with engine.connect() as c:
        assert c.scalar(select(m.Agency.consumed_cents).where(m.Agency.id==agency)) == 100
    engine.dispose()


def test_partial_schema_adoption_rolls_back_without_stamping(database_factory):
    url = database_factory(migrate=False)
    engine = create_engine(url)
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE agencies (id uuid PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="Unsupported legacy schema"):
        upgrade_database(url, adopt=True)
    with engine.connect() as c:
        assert inspect(c).get_table_names() == ["agencies"]
        assert not any(s.startswith("baseline_check_") for s in inspect(c).get_schema_names())
    engine.dispose()


def test_legacy_adoption_transfers_admin_owned_tables_to_migration_role(database_factory):
    url = database_factory(migrate=False)
    credentials = make_url(os.environ["PROOFPAY_TEST_DATABASE_URL"])
    admin_url = url.set(username=credentials.username, password=credentials.password)
    admin = create_engine(admin_url)
    with admin.begin() as c:
        c.exec_driver_sql((MIGRATIONS/"versions/0001_runtime_baseline.sql").read_text())
    upgrade_database(admin_url, adopt=True)
    upgrade_database(url)
    with admin.connect() as c:
        owners = c.execute(text(
            "SELECT DISTINCT pg_get_userbyid(relowner) FROM pg_class c "
            "JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname='public' AND c.relkind='r'"
        )).scalars().all()
        assert owners == ["proofpay_migrator"]
    admin.dispose()


def test_invalid_baseline_data_blocks_entire_upgrade(database_factory):
    url = database_factory(migrate=False)
    engine = create_engine(url)
    with engine.begin() as c:
        command.upgrade(alembic_config(c), "0001_runtime_baseline")
        c.execute(m.Agency.__table__.insert().values(name="Bad", advisory_lock_key=98, principal_limit_cents=500))
        agency = c.scalar(select(m.Agency.id))
        for _ in range(2):
            c.execute(m.DemoRun.__table__.insert().values(agency_id=agency, state="active"))
    with pytest.raises(IntegrityError):
        upgrade_database(url)
    with engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0001_runtime_baseline"
        assert c.scalar(text("SELECT count(*) FROM demo_runs")) == 2
        assert "created_at" not in {col["name"] for col in inspect(c).get_columns("verification_jobs")}
    engine.dispose()


def test_cross_agency_foreign_key_cannot_reference_real_foreign_actor(pg_engine, graph):
    other_agency = uuid.uuid4()
    with pg_engine.begin() as c:
        c.execute(m.Agency.__table__.insert().values(id=other_agency, name="Other tenant", advisory_lock_key=other_agency.int % (2**62), principal_limit_cents=1000))
    rejection(pg_engine, m.Brief.__table__.insert().values(agency_id=other_agency, created_by=graph["owner"]), "23503")


def test_same_agency_current_pointer_cannot_reference_another_tasks_version(pg_engine, graph):
    with pg_engine.begin() as c:
        another_brief = uuid.uuid4()
        another_task = uuid.uuid4()
        another_mandate = uuid.uuid4()
        c.execute(m.Brief.__table__.insert().values(id=another_brief, agency_id=graph["agency"], created_by=graph["owner"]))
        c.execute(m.DeliveryTask.__table__.insert().values(id=another_task, agency_id=graph["agency"], demo_run_id=graph["run"], brief_id=another_brief))
        c.execute(m.Mandate.__table__.insert().values(id=another_mandate, agency_id=graph["agency"], task_id=another_task))
    rejection(pg_engine, m.Mandate.__table__.update().where(m.Mandate.id==another_mandate).values(current_version_id=graph["version"]), "23503")


@pytest.mark.parametrize("model,key,field,value", [
    (m.RecipientBinding,"binding","receiver_hash","b"*64),
    (m.BriefRevision,"revision","body","Edited"),
    (m.Delivery,"delivery","claim","Edited"),
    (m.EvidenceBundle,"bundle","bundle_digest","b"*64),
    (m.AIInteraction,"review","output",{}),
])
def test_source_history_cannot_be_edited_or_deleted(pg_engine, graph, model, key, field, value):
    rejection(pg_engine, model.__table__.update().where(model.id==graph[key]).values({field:value}))
    rejection(pg_engine, model.__table__.delete().where(model.id==graph[key]))


def test_audit_is_append_only_and_attributable(pg_engine, graph):
    with pg_engine.begin() as c:
        audit = uuid.uuid4()
        c.execute(m.AuditLog.__table__.insert().values(id=audit, agency_id=graph["agency"], service_actor="test", event_type="test", correlation_id=uuid.uuid4(), references_json={}, details={}))
    rejection(pg_engine, m.AuditLog.__table__.update().where(m.AuditLog.id==audit).values(details={"edited":True}))
    rejection(pg_engine, m.AuditLog.__table__.delete().where(m.AuditLog.id==audit))
    rejection(pg_engine, m.AuditLog.__table__.insert().values(agency_id=graph["agency"], event_type="unattributed", correlation_id=uuid.uuid4(), references_json={}, details={}))


def test_approved_snapshot_and_checks_remain_frozen_after_supersession(pg_engine, graph):
    rejection(pg_engine, m.MandateVersion.__table__.update().where(m.MandateVersion.id==graph["version"]).values(amount_cents=200))
    rejection(pg_engine, m.AcceptanceCheck.__table__.update().where(m.AcceptanceCheck.id==graph["check1"]).values(params={"edit":True}))
    with pg_engine.begin() as c:
        c.execute(m.MandateVersion.__table__.update().where(m.MandateVersion.id==graph["version"]).values(lifecycle_state="superseded"))
    rejection(pg_engine, m.MandateVersion.__table__.update().where(m.MandateVersion.id==graph["version"]).values(lifecycle_state="draft", approved_at=None, approved_by=None))
    rejection(pg_engine, m.AcceptanceCheck.__table__.delete().where(m.AcceptanceCheck.id==graph["check1"]))


def test_approval_requires_exactly_three_approved_checks_at_commit(pg_engine, graph):
    with pg_engine.begin() as c:
        c.execute(m.MandateVersion.__table__.update().where(m.MandateVersion.id==graph["version"]).values(lifecycle_state="superseded"))
    with pytest.raises(IntegrityError, match="three approved checks"):
        with pg_engine.begin() as c:
            c.execute(m.MandateVersion.__table__.insert().values(agency_id=graph["agency"], task_id=graph["task"], mandate_id=graph["mandate"], version=2, brief_revision_id=graph["revision"], compilation_id=graph["compilation"], contractor_id=graph["contractor"], recipient_binding_id=graph["binding"], amount_cents=100, principal_cap_cents=300, expires_at=text("now()+interval '1 day'"), public_payload={}, payload_digest=DIGEST, lifecycle_state="approved", approved_by=graph["owner"], approved_at=text("now()")))


def test_attempt_identity_and_terminal_history_cannot_regress(pg_engine, graph):
    rejection(pg_engine, m.PaymentAttempt.__table__.update().where(m.PaymentAttempt.id==graph["attempt"]).values(sender_item_id="changed"))
    with pg_engine.begin() as c:
        c.execute(m.PaymentAttempt.__table__.update().where(m.PaymentAttempt.id==graph["attempt"]).values(state="success", successful=True, unresolved=False))
    rejection(pg_engine, m.PaymentAttempt.__table__.update().where(m.PaymentAttempt.id==graph["attempt"]).values(state="prepared", successful=False, unresolved=True))
    rejection(pg_engine, m.PaymentAttempt.__table__.delete().where(m.PaymentAttempt.id==graph["attempt"]))


def test_one_obligation_and_unresolved_attempt_per_task(pg_engine, graph):
    rejection(pg_engine, m.PaymentObligation.__table__.insert().values(agency_id=graph["agency"], task_id=graph["task"]), "23505")
    rejection(pg_engine, m.PaymentAttempt.__table__.insert().values(**attempt_values(graph, 2)), "23505")


def test_concurrent_attempt_initiation_has_exactly_one_winner(pg_engine, graph):
    with pg_engine.begin() as c:
        c.execute(m.PaymentAttempt.__table__.update().where(m.PaymentAttempt.id==graph["attempt"]).values(state="failed", unresolved=False, nonpayment_confirmed=True))

    simultaneous = Barrier(2)

    def attempt(number):
        try:
            with pg_engine.begin() as c:
                simultaneous.wait(timeout=5)
                c.execute(m.PaymentAttempt.__table__.insert().values(**attempt_values(graph, number)))
            return "accepted"
        except IntegrityError as error:
            assert error.orig.sqlstate == "23505"
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, [2,3])) == ["accepted","rejected"]


def test_one_successful_attempt_ever_even_after_task_state_changes(pg_engine, graph):
    with pg_engine.begin() as c:
        c.execute(m.PaymentAttempt.__table__.update().where(m.PaymentAttempt.id==graph["attempt"]).values(state="success", successful=True, unresolved=False))
        c.execute(m.DeliveryTask.__table__.update().where(m.DeliveryTask.id==graph["task"]).values(state="paid"))
    values = {**attempt_values(graph,2), "state":"success", "successful":True, "unresolved":False}
    rejection(pg_engine, m.PaymentAttempt.__table__.insert().values(**values), "23505")


def test_ledger_phase_posts_once_with_consistent_deltas(pg_engine, graph):
    values = dict(agency_id=graph["agency"], obligation_id=graph["obligation"], attempt_id=graph["attempt"], phase="reservation", kind="reserve", principal_cents=100, reserved_delta=100, consumed_delta=0)
    with pg_engine.begin() as c:
        c.execute(m.BudgetEntry.__table__.insert().values(**values))
    rejection(pg_engine, m.BudgetEntry.__table__.insert().values(**values), "23505")
    rejection(pg_engine, m.BudgetEntry.__table__.insert().values(**{**values,"phase":"disposition","kind":"consume","reserved_delta":0,"consumed_delta":100}))
    disposition = {**values,"phase":"disposition","kind":"consume","reserved_delta":-100,"consumed_delta":100}
    with pg_engine.begin() as c:
        c.execute(m.BudgetEntry.__table__.insert().values(**disposition))
    rejection(pg_engine, m.BudgetEntry.__table__.insert().values(**{**disposition,"kind":"release","consumed_delta":0}), "23505")
    rejection(pg_engine, m.BudgetEntry.__table__.update().where(m.BudgetEntry.attempt_id==graph["attempt"]).values(principal_cents=200))


def test_ledger_proof_cannot_belong_to_another_attempt(pg_engine, graph):
    with pg_engine.begin() as c:
        c.execute(m.PaymentAttempt.__table__.update().where(m.PaymentAttempt.id==graph["attempt"]).values(state="failed", unresolved=False, nonpayment_confirmed=True))
        other_attempt = uuid.uuid4()
        proof = uuid.uuid4()
        c.execute(m.PaymentAttempt.__table__.insert().values(id=other_attempt, **attempt_values(graph, 2)))
        c.execute(m.ProviderObservation.__table__.insert().values(id=proof, agency_id=graph["agency"], attempt_id=other_attempt, operation="test", response_digest=DIGEST, redacted_response={"test_double":True}, binding_verified=False))
    rejection(pg_engine, m.BudgetEntry.__table__.insert().values(agency_id=graph["agency"], obligation_id=graph["obligation"], attempt_id=graph["attempt"], phase="disposition", kind="release", principal_cents=100, reserved_delta=-100, consumed_delta=0, proof_observation_id=proof), "23503")


def test_command_receipt_scope_is_unique_and_source_is_immutable(pg_engine, graph):
    values = dict(agency_id=graph["agency"], principal_user_id=graph["owner"], effective_user_id=graph["owner"], operation="test_only", idempotency_key=uuid.uuid4(), request_digest=DIGEST, http_status=202, response={"test_double":True})
    receipt = uuid.uuid4()
    with pg_engine.begin() as c:
        c.execute(m.CommandReceipt.__table__.insert().values(id=receipt, **values))
    rejection(pg_engine, m.CommandReceipt.__table__.insert().values(**values), "23505")
    rejection(pg_engine, m.CommandReceipt.__table__.update().where(m.CommandReceipt.id==receipt).values(response={"rewritten":True}))
    with pg_engine.begin() as c:
        c.execute(m.CommandReceipt.__table__.insert().values(**{**values,"operation":"different_family"}))


def test_provider_success_requires_matched_item_identity(pg_engine, graph):
    rejection(pg_engine, m.PayoutItem.__table__.update().where(m.PayoutItem.id==graph["item"]).values(canonical_state="success", raw_status="SUCCESS"))


@pytest.mark.parametrize("size,media", [(524289,"image/png"),(65537,"application/json")])
def test_evidence_byte_limits_at_database_boundary(pg_engine, graph, size, media):
    rejection(pg_engine, m.EvidenceArtifact.__table__.insert().values(agency_id=graph["agency"], bundle_id=graph["bundle"], media_type=media, digest=DIGEST, content=b"x"*size))


def test_webhook_quarantine_is_immutable_and_unverified_event_cannot_deduplicate(pg_engine, graph):
    delivery = uuid.uuid4()
    with pg_engine.begin() as c:
        c.execute(m.WebhookDelivery.__table__.insert().values(id=delivery, agency_id=graph["agency"], claimed_event_id="test-event", transmission_id="test-transmission", raw_body=b"{}", payload_digest=DIGEST, headers={}, verification_state="pending"))
    event = dict(agency_id=graph["agency"], provider_event_id="test-event", delivery_id=delivery, payload_digest=DIGEST, event_type="test", verified_at=text("now()"))
    rejection(pg_engine, m.WebhookEvent.__table__.insert().values(**event))
    rejection(pg_engine, m.WebhookDelivery.__table__.update().where(m.WebhookDelivery.id==delivery).values(raw_body=b"edited"))
    with pg_engine.begin() as c:
        c.execute(m.WebhookDelivery.__table__.update().where(m.WebhookDelivery.id==delivery).values(verification_state="verified"))
        c.execute(m.WebhookEvent.__table__.insert().values(**event))
    rejection(pg_engine, m.WebhookEvent.__table__.insert().values(**event), "23505")


@pytest.mark.parametrize("statement", [
    "INSERT INTO payment_attempts SELECT * FROM payment_attempts WHERE false",
    "INSERT INTO budget_entries SELECT * FROM budget_entries WHERE false",
    "INSERT INTO provider_observations SELECT * FROM provider_observations WHERE false",
    "UPDATE agencies SET consumed_cents=consumed_cents+1",
    "UPDATE payout_items SET canonical_state='success'",
    "UPDATE payment_obligations SET next_attempt_no=next_attempt_no+1",
    "UPDATE webhook_deliveries SET verification_state='verified'",
    "CREATE TABLE unauthorized (id integer)",
    "TRUNCATE audit_log",
    "SELECT receiver_ciphertext FROM recipient_bindings",
    "SELECT request_ciphertext FROM payment_attempts",
    "SET ROLE proofpay_migrator",
])
def test_api_login_cannot_bypass_financial_or_schema_authority(postgres_url, statement):
    api = create_engine(postgres_url.set(username="proofpay_api", password=PASSWORDS["proofpay_api"]))
    try:
        rejection(api, text(statement), "42501")
    finally:
        api.dispose()


def test_api_cannot_mark_task_paid_but_executor_can(postgres_url, pg_engine, graph):
    api = create_engine(postgres_url.set(username="proofpay_api", password=PASSWORDS["proofpay_api"]))
    rejection(api, m.DeliveryTask.__table__.update().where(m.DeliveryTask.id==graph["task"]).values(state="paid"), "42501")
    executor = create_engine(postgres_url.set(username="proofpay_executor", password=PASSWORDS["proofpay_executor"]))
    with executor.begin() as c:
        c.execute(m.DeliveryTask.__table__.update().where(m.DeliveryTask.id==graph["task"]).values(state="paid"))
    api.dispose()
    executor.dispose()


def test_api_cannot_insert_paid_task_or_funded_obligation(postgres_url, pg_engine, graph):
    brief = uuid.uuid4()
    with pg_engine.begin() as c:
        c.execute(m.Brief.__table__.insert().values(id=brief, agency_id=graph["agency"], created_by=graph["owner"]))
    api = create_engine(postgres_url.set(username="proofpay_api", password=PASSWORDS["proofpay_api"]))
    rejection(api, m.DeliveryTask.__table__.insert().values(agency_id=graph["agency"], demo_run_id=graph["run"], brief_id=brief, state="paid"), "42501")
    rejection(api, m.PaymentObligation.__table__.insert().values(agency_id=graph["agency"], task_id=graph["task"], consumed_cents=100), "42501")
    api.dispose()


def test_api_can_create_initial_obligation_with_only_server_owned_zero_balances(postgres_url, pg_engine, graph):
    api = create_engine(postgres_url.set(username="proofpay_api", password=PASSWORDS["proofpay_api"]))
    with Session(api) as session:
        brief = m.Brief(agency_id=graph["agency"], created_by=graph["owner"])
        session.add(brief)
        session.flush()
        task = m.DeliveryTask(agency_id=graph["agency"], demo_run_id=graph["run"], brief_id=brief.id)
        session.add(task)
        session.flush()
        obligation = m.PaymentObligation(agency_id=graph["agency"], task_id=task.id)
        session.add(obligation)
        session.commit()
        session.refresh(obligation)
        assert (obligation.next_attempt_no, obligation.reserved_cents, obligation.consumed_cents) == (1,0,0)
    api.dispose()


def test_api_reads_redacted_orm_projections_and_queues_decisions(postgres_url, graph):
    api = create_engine(postgres_url.set(username="proofpay_api", password=PASSWORDS["proofpay_api"]))
    with Session(api) as session:
        attempt = session.get(m.PaymentAttempt, graph["attempt"])
        assert attempt.principal_cents == 100
        assert "request_ciphertext" not in attempt.__dict__
        assert session.get(m.RecipientBinding, graph["binding"]).receiver_hash == DIGEST
        session.add(m.OutboxEvent(agency_id=graph["agency"], task_id=graph["task"], event_type="test_only", dedup_key=uuid.uuid4().hex, payload={}))
        session.add(m.AuditLog(agency_id=graph["agency"], service_actor="test", event_type="test", correlation_id=uuid.uuid4(), references_json={}, details={}))
        session.commit()
    api.dispose()


def test_executor_login_cannot_change_funding_or_approved_terms(postgres_url, graph):
    executor = create_engine(postgres_url.set(username="proofpay_executor", password=PASSWORDS["proofpay_executor"]))
    rejection(executor, m.Agency.__table__.update().where(m.Agency.id==graph["agency"]).values(principal_limit_cents=20000), "42501")
    rejection(executor, m.MandateVersion.__table__.update().where(m.MandateVersion.id==graph["version"]).values(amount_cents=200), "42501")
    executor.dispose()
