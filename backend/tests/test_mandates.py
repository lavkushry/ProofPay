"""Real PostgreSQL/HTTP approval; compiler and financial inputs are explicit doubles."""

import asyncio
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from backend import worker
from backend.app import models as m
from backend.app.config import settings
from backend.app.schemas.api_schemas import CheckProposal
from backend.app.schemas.mandates import MandateResponse, MandateVersionResponse
from backend.app.services import commands, outbox
from backend.app.services.compiler import CompilerError, CompileResult, compilation_input
from backend.tests.postgres_support import database_factory, graph, pg_engine, postgres_url
from backend.tests.test_workflows import brief_body, expire, headers, login, workspace

pytestmark = pytest.mark.postgres


@pytest.fixture
def approval_workspace(workspace, pg_engine, monkeypatch):
    client, ids, factory = workspace
    with pg_engine.begin() as c:
        c.execute(update(m.Contractor).where(m.Contractor.id==ids["contractor"]).values(current_binding_id=ids["binding"]))
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("test-only-key"))

    async def compiler_double(contract, revision, **kwargs):
        checks = [{"check_id": f"C0{i}", "template_type": t.template_type, "params": t.params,
                   "compiled_by": "ai", "approved": False} for i, t in enumerate(contract.family(revision.family).templates, 1)]
        proposal = CheckProposal(checks=checks, ambiguities=[], clarifying_questions=[])
        _prompt, digest = compilation_input(contract, revision)
        return CompileResult(proposal, "ready", "openai", "explicit-test-double", "compiler-v0.1",
            "proofpay-tools-v0.1", digest, commands.canonical_digest(proposal.model_dump(mode="json")), None)

    monkeypatch.setattr(worker, "compile_revision", compiler_double)
    session = login(client)
    return client, ids, factory, session


def compile_brief(client, factory, session, brief):
    result = client.post(f"/api/briefs/{brief['id']}/compile", json={
        "expected_revision": brief["revision"], "expected_digest": brief["digest"]}, headers=headers(session))
    assert result.status_code == 202, result.text
    for _ in range(10):
        lease = asyncio.run(outbox.claim(factory))
        assert lease is not None
        asyncio.run(worker.process_lease(factory, lease))
        if str(lease.id) == result.json()["job_id"]:
            break
    else:
        pytest.fail("Compile job was not processed")
    return result.json()


def compiled(approval_workspace, family="responsive_css"):
    client, ids, factory, session = approval_workspace
    body = brief_body()
    body["family"] = family
    response = client.post("/api/briefs", json=body, headers=headers(session))
    assert response.status_code == 201, response.text
    brief = response.json()
    compilation = compile_brief(client, factory, session, brief)
    request = {"task_id": brief["task_id"], "brief_revision_id": brief["revision_id"],
               "compilation_id": compilation["compilation_id"], "terms": brief["terms"]}
    return brief, compilation, request


def draft(client, session, request):
    response = client.post("/api/mandates", json=request, headers=headers(session))
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, session, version, current=None, key=None):
    return client.post(f"/api/mandates/{version['mandate_id']}/versions/{version['id']}/approve",
        json={"expected_draft_digest": version["digest"], "expected_current_version_id": current}, headers=headers(session, key))


def replacement(client, session, request, mandate_id, current):
    body = {k: v for k, v in request.items() if k != "task_id"}
    body["expected_current_version_id"] = current
    response = client.post(f"/api/mandates/{mandate_id}/versions", json=body, headers=headers(session))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("family", ["responsive_css", "api_endpoint", "keyboard_accessibility"])
def test_exact_approval_freezes_three_checks_and_receipt(approval_workspace, pg_engine, family):
    client, ids, factory, session = approval_workspace
    brief, compilation, request = compiled(approval_workspace, family)
    key = uuid.uuid4()
    first = client.post("/api/mandates", json=request, headers=headers(session, key))
    assert first.status_code == 201, first.text
    version = first.json()
    MandateVersionResponse.model_validate(version)
    assert version["snapshot"]["status"] == "draft" and version["snapshot"]["audit"]["approved_at"] is None
    assert client.post("/api/mandates", json=request, headers=headers(session, key)).json() == version
    assert client.get(f"/api/mandates/{version['mandate_id']}").json()["current_version_id"] is None
    wrong = {**request, "terms": {**request["terms"], "max_attempts": 2}}
    assert client.post("/api/mandates", json=wrong, headers=headers(session, key)).json()["code"] == "IDEMPOTENCY_CONFLICT"
    approval_key = uuid.uuid4()
    response = approve(client, session, version, key=approval_key)
    assert response.status_code == 200, response.text
    approved = response.json()
    MandateVersionResponse.model_validate(approved)
    assert approved["digest"] != version["digest"]
    assert approved["digest"] == commands.canonical_digest(approved["snapshot"])
    assert approved["snapshot"]["audit"]["approved_by"] == str(ids["owner"])
    assert approved["snapshot"]["audit"]["immutable"] is True
    assert all(c["approved"] is True and c["compiled_by"] == "ai" for c in approved["snapshot"]["acceptance_checks"])
    assert approve(client, session, version, key=approval_key).json() == approved
    assert approve(client, session, version).status_code == 409
    public = client.get(f"/api/mandates/{version['mandate_id']}").json()
    MandateResponse.model_validate(public)
    assert public["current_version_id"] == approved["id"] and public["versions"] == [approved]
    with pg_engine.connect() as c:
        task = c.execute(select(m.DeliveryTask.__table__).where(m.DeliveryTask.id==uuid.UUID(brief["task_id"]))).mappings().one()
        assert task["state"] == "awaiting_delivery" and task["version"] == 2
        assert c.scalar(select(func.count()).select_from(m.PaymentObligation).where(m.PaymentObligation.task_id==task["id"])) == 1
        assert c.scalar(select(m.MandateVersion.recipient_binding_id).where(m.MandateVersion.id==uuid.UUID(approved["id"]))) == ids["binding"]
    with pytest.raises(IntegrityError), pg_engine.begin() as c:
        c.execute(update(m.MandateVersion).where(m.MandateVersion.id==uuid.UUID(approved["id"])).values(amount_cents=1))
    with pytest.raises(IntegrityError), pg_engine.begin() as c:
        c.execute(update(m.AcceptanceCheck).where(m.AcceptanceCheck.mandate_version_id==uuid.UUID(approved["id"])).values(params={}))
    # Durable approval jobs record history without triggering delivery or payment work.
    while (lease := asyncio.run(outbox.claim(factory))) is not None:
        asyncio.run(worker.process_lease(factory, lease))
    with pg_engine.connect() as c:
        assert not c.scalar(select(m.OutboxEvent.id).where(m.OutboxEvent.task_id==uuid.UUID(brief["task_id"]), m.OutboxEvent.state!="done"))


def test_snapshot_pins_recipient_after_directory_edits(approval_workspace, pg_engine):
    client, ids, _, session = approval_workspace
    _, _, request = compiled(approval_workspace)
    version = draft(client, session, request)
    response = approve(client, session, version)
    assert response.status_code == 200
    frozen = response.json()
    new_binding = uuid.uuid4()
    with pg_engine.begin() as c:
        c.execute(m.RecipientBinding.__table__.insert().values(id=new_binding, agency_id=ids["agency"], contractor_id=ids["contractor"],
            receiver_ciphertext=b"new-test-only-address", receiver_hash="b"*64, key_version="test", confirmed_at=datetime.now(timezone.utc)))
        c.execute(update(m.Contractor).where(m.Contractor.id==ids["contractor"]).values(current_binding_id=new_binding, display_name="Renamed"))
    assert client.get(f"/api/mandates/{version['mandate_id']}/versions/{version['id']}").json() == frozen
    with pg_engine.connect() as c:
        assert c.scalar(select(m.MandateVersion.recipient_binding_id).where(m.MandateVersion.id==uuid.UUID(version["id"]))) == ids["binding"]
    assert "ciphertext" not in str(frozen) and "receiver" not in str(frozen)


def test_contractor_reads_only_own_approved_versions(approval_workspace):
    client, _, _, session = approval_workspace
    _, _, request = compiled(approval_workspace)
    version = draft(client, session, request)
    url = f"/api/mandates/{version['mandate_id']}"
    version_url = f"{url}/versions/{version['id']}"
    maya = login(client, "contractor_maya", "maya-code")
    assert client.get(url).status_code == 404 and client.get(version_url).status_code == 404
    assert approve(client, maya, version).status_code == 403
    session = login(client)
    assert client.post(f"{version_url}/approve", json={"expected_draft_digest": version["digest"], "expected_current_version_id": None}).status_code == 403
    assert approve(client, session, version).status_code == 200
    login(client, "contractor_leo", "leo-code")
    assert client.get(url).status_code == 404 and client.get(version_url).status_code == 404
    login(client, "contractor_maya", "maya-code")
    assert client.get(url).status_code == 200 and client.get(version_url).status_code == 200
    assert client.get(f"/api/mandates/{uuid.uuid4()}/versions/{version['id']}").status_code == 404


@pytest.mark.parametrize("change,code", [
    ("digest", "STALE_MANDATE"), ("pointer", "STALE_MANDATE"), ("revision", "STALE_REVISION"),
    ("expired", "MANDATE_EXPIRED"), ("checks", "STALE_MANDATE"), ("projection", "STALE_COMPILATION"),
    ("ambiguous", "COMPILATION_NOT_READY"), ("recipient", "STALE_RECIPIENT"), ("inactive", "STALE_TASK"),
])
def test_approval_rejects_stale_or_inconsistent_records(approval_workspace, pg_engine, change, code):
    client, ids, _, session = approval_workspace
    brief, compilation, request = compiled(approval_workspace)
    version = draft(client, session, request)
    current = None
    with pg_engine.begin() as c:
        if change == "digest":
            version["digest"] = "f"*64
        elif change == "pointer":
            current = str(uuid.uuid4())
        elif change == "expired":
            c.execute(update(m.MandateVersion).where(m.MandateVersion.id==uuid.UUID(version["id"])).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
        elif change == "checks":
            c.execute(update(m.AcceptanceCheck).where(m.AcceptanceCheck.mandate_version_id==uuid.UUID(version["id"])).values(params={"tampered": True}))
        elif change == "projection":
            proposal = copy.deepcopy(version["snapshot"]["acceptance_checks"])
            proposal[0]["params"] = {"target_ref": "injected"}
            c.execute(update(m.Compilation).where(m.Compilation.id==uuid.UUID(compilation["compilation_id"])).values(proposal={"checks": proposal, "ambiguities": [], "clarifying_questions": []}))
        elif change == "ambiguous":
            c.execute(update(m.Compilation).where(m.Compilation.id==uuid.UUID(compilation["compilation_id"])).values(status="ambiguous"))
        elif change == "recipient":
            binding_id = uuid.uuid4()
            c.execute(m.RecipientBinding.__table__.insert().values(id=binding_id, agency_id=ids["agency"], contractor_id=ids["contractor"],
                receiver_ciphertext=b"other", receiver_hash="b"*64, key_version="test", confirmed_at=datetime.now(timezone.utc)))
            c.execute(update(m.Contractor).where(m.Contractor.id==ids["contractor"]).values(current_binding_id=binding_id))
        elif change == "inactive":
            c.execute(update(m.DemoRun).where(m.DemoRun.id==ids["run"]).values(state="archived"))
    if change == "revision":
        body = brief_body()
        body.pop("fixture_ref")
        body["expected_revision"] = 1
        response = client.post(f"/api/briefs/{brief['id']}/revisions", json=body, headers=headers(session))
        assert response.status_code == 201, response.text
    response = approve(client, session, version, current)
    assert response.status_code == 409 and response.json()["code"] == code, response.text
    with pg_engine.connect() as c:
        assert c.scalar(select(m.Mandate.current_version_id).where(m.Mandate.id==uuid.UUID(version["mandate_id"]))) is None
        assert c.scalar(select(m.MandateVersion.lifecycle_state).where(m.MandateVersion.id==uuid.UUID(version["id"]))) == "draft"
        assert not c.scalar(select(m.AcceptanceCheck.id).where(m.AcceptanceCheck.mandate_version_id==uuid.UUID(version["id"]), m.AcceptanceCheck.approved.is_(True)))


def test_missing_binding_and_foreign_lineage_cannot_create_authority(approval_workspace, pg_engine):
    client, ids, _, session = approval_workspace
    _, _, request = compiled(approval_workspace)
    for field in ("task_id", "brief_revision_id", "compilation_id"):
        response = client.post("/api/mandates", json={**request, field: str(uuid.uuid4())}, headers=headers(session))
        assert response.status_code in (404, 409), response.text
    with pg_engine.begin() as c:
        c.execute(update(m.Contractor).where(m.Contractor.id==ids["contractor"]).values(current_binding_id=None))
    response = client.post("/api/mandates", json=request, headers=headers(session))
    assert response.status_code == 503 and response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_concurrent_approval_has_one_winner_and_durable_replay(approval_workspace, pg_engine):
    client, _, _, session = approval_workspace
    _, _, request = compiled(approval_workspace)
    version = draft(client, session, request)
    other = replacement(client, session, request, version["mandate_id"], None)
    keys = [uuid.uuid4(), uuid.uuid4()]
    versions = [version, other]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda i: approve(client, session, versions[i], key=keys[i]), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(i for i, r in enumerate(responses) if r.status_code == 200)
    assert approve(client, session, versions[winner], key=keys[winner]).json() == responses[winner].json()
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.MandateVersion).where(m.MandateVersion.mandate_id==uuid.UUID(version["mandate_id"]), m.MandateVersion.lifecycle_state=="approved")) == 1


def test_replacement_preserves_snapshot_obligation_and_invalidates_old_evidence(approval_workspace, pg_engine):
    client, _, _, session = approval_workspace
    brief, _, request = compiled(approval_workspace)
    first = draft(client, session, request)
    approved = approve(client, session, first).json()
    task_id = uuid.UUID(brief["task_id"])
    with pg_engine.connect() as c:
        obligation = c.execute(select(m.PaymentObligation.__table__).where(m.PaymentObligation.task_id==task_id)).mappings().one()
    second = replacement(client, session, request, first["mandate_id"], first["id"])
    assert client.get(f"/api/mandates/{first['mandate_id']}").json()["current_version_id"] == first["id"]
    response = approve(client, session, second, first["id"])
    assert response.status_code == 200, response.text
    historical = client.get(f"/api/mandates/{first['mandate_id']}/versions/{first['id']}").json()
    assert historical == {**approved, "lifecycle_state": "superseded"}
    with pg_engine.connect() as c:
        assert dict(c.execute(select(m.PaymentObligation.__table__).where(m.PaymentObligation.task_id==task_id)).mappings().one()) == dict(obligation)
        task = c.execute(select(m.DeliveryTask.__table__).where(m.DeliveryTask.id==task_id)).mappings().one()
        assert task["current_bundle_id"] is None and task["current_delivery_id"] is None and task["version"] == 3


def test_expired_worker_cannot_allocate_calls_or_change_compilation(approval_workspace, pg_engine):
    client, _, factory, session = approval_workspace
    result = client.post("/api/briefs", json=brief_body(), headers=headers(session)).json()
    pending = client.post(f"/api/briefs/{result['id']}/compile", json={"expected_revision": 1, "expected_digest": result["digest"]}, headers=headers(session)).json()
    lease = asyncio.run(outbox.claim(factory))
    asyncio.run(worker.process_lease(factory, lease))  # capture
    lease = asyncio.run(outbox.claim(factory))
    assert str(lease.id) == pending["job_id"]
    revision, contract = asyncio.run(worker._compile_input(factory, lease))
    expire(pg_engine, lease)
    with pytest.raises(outbox.LeaseLost):
        asyncio.run(worker._record_compile_start(factory, lease, revision, contract))
    with pytest.raises(outbox.LeaseLost):
        asyncio.run(worker._mark_compilation_running(factory, lease))
    with pg_engine.connect() as c:
        assert c.scalar(select(m.Compilation.status).where(m.Compilation.id==uuid.UUID(pending["compilation_id"]))) == "queued"
        assert c.scalar(select(func.count()).select_from(m.AIInteraction).where(m.AIInteraction.job_id==lease.id)) == 0


def original_replacement(approval_workspace):
    client, ids, factory, session = approval_workspace
    body = brief_body()
    body.pop("fixture_ref")
    body["expected_revision"] = 1
    body["terms"]["amount"]["value"] = "1.00"
    body["terms"]["principal_cap"]["value"] = "3.00"
    revised = client.post(f"/api/briefs/{ids['brief']}/revisions", json=body, headers=headers(session))
    assert revised.status_code == 201, revised.text
    brief = revised.json()
    compilation = compile_brief(client, factory, session, brief)
    request = {"brief_revision_id": brief["revision_id"], "compilation_id": compilation["compilation_id"], "terms": brief["terms"]}
    return request


def test_supersession_preserves_unresolved_attempt_and_reservation(approval_workspace, pg_engine):
    client, ids, _, session = approval_workspace
    request = original_replacement(approval_workspace)
    with pg_engine.begin() as c:
        c.execute(update(m.Agency).where(m.Agency.id==ids["agency"]).values(reserved_cents=100))
        c.execute(update(m.PaymentObligation).where(m.PaymentObligation.id==ids["obligation"]).values(reserved_cents=100, next_attempt_no=2))
        c.execute(update(m.DeliveryTask).where(m.DeliveryTask.id==ids["task"]).values(state="reconciling"))
    with pg_engine.connect() as c:
        before_attempt = dict(c.execute(select(m.PaymentAttempt.__table__).where(m.PaymentAttempt.id==ids["attempt"])).mappings().one())
        before_obligation = dict(c.execute(select(m.PaymentObligation.__table__).where(m.PaymentObligation.id==ids["obligation"])).mappings().one())
        before_snapshot = c.scalar(select(m.MandateVersion.public_payload).where(m.MandateVersion.id==ids["version"]))
    version = replacement(client, session, request, str(ids["mandate"]), str(ids["version"]))
    response = approve(client, session, version, str(ids["version"]))
    assert response.status_code == 200, response.text
    with pg_engine.connect() as c:
        assert dict(c.execute(select(m.PaymentAttempt.__table__).where(m.PaymentAttempt.id==ids["attempt"])).mappings().one()) == before_attempt
        assert dict(c.execute(select(m.PaymentObligation.__table__).where(m.PaymentObligation.id==ids["obligation"])).mappings().one()) == before_obligation
        assert c.scalar(select(m.Agency.reserved_cents).where(m.Agency.id==ids["agency"])) == 100
        assert c.scalar(select(m.EvidenceBundle.id).where(m.EvidenceBundle.id==ids["bundle"])) == ids["bundle"]
        assert c.scalar(select(m.MandateVersion.public_payload).where(m.MandateVersion.id==ids["version"])) == before_snapshot
        task = c.execute(select(m.DeliveryTask.__table__).where(m.DeliveryTask.id==ids["task"])).mappings().one()
        assert task["state"] == "reconciling" and task["hold_reasons"] == ["PAYMENT_IN_PROGRESS"]
        assert task["current_bundle_id"] is None


@pytest.mark.parametrize("history,code", [("settled", "OBLIGATION_SETTLED"), ("principal", "BUDGET_EXCEEDED"), ("attempts", "ATTEMPT_LIMIT")])
def test_replacement_cannot_reset_financial_limits(approval_workspace, pg_engine, history, code):
    client, ids, _, session = approval_workspace
    request = original_replacement(approval_workspace)
    version = replacement(client, session, request, str(ids["mandate"]), str(ids["version"]))
    with pg_engine.begin() as c:
        if history == "settled":
            c.execute(update(m.PaymentAttempt).where(m.PaymentAttempt.id==ids["attempt"]).values(successful=True, unresolved=False, state="success"))
            c.execute(update(m.PaymentObligation).where(m.PaymentObligation.id==ids["obligation"]).values(success_attempt_id=ids["attempt"]))
        elif history == "principal":
            c.execute(update(m.PaymentObligation).where(m.PaymentObligation.id==ids["obligation"]).values(reserved_cents=301))
        else:
            c.execute(update(m.PaymentObligation).where(m.PaymentObligation.id==ids["obligation"]).values(next_attempt_no=3))
            payload = copy.deepcopy(version["snapshot"])
            payload["budget"]["max_attempts"] = 1
            version["digest"] = commands.canonical_digest(payload)
            c.execute(update(m.MandateVersion).where(m.MandateVersion.id==uuid.UUID(version["id"])).values(
                max_attempts=1, public_payload=payload, payload_digest=version["digest"]))
    result = approve(client, session, version, str(ids["version"]))
    assert result.status_code == 409 and result.json()["code"] == code, result.text
    with pg_engine.connect() as c:
        assert c.scalar(select(m.Mandate.current_version_id).where(m.Mandate.id==ids["mandate"])) == ids["version"]


def test_call_budget_and_failure_mutations_require_current_lease(approval_workspace, pg_engine):
    client, _, factory, session = approval_workspace
    brief = client.post("/api/briefs", json=brief_body(), headers=headers(session)).json()
    client.post(f"/api/briefs/{brief['id']}/compile", json={"expected_revision": 1, "expected_digest": brief["digest"]}, headers=headers(session))
    capture = asyncio.run(outbox.claim(factory))
    asyncio.run(worker.process_lease(factory, capture))
    lease = asyncio.run(outbox.claim(factory))
    revision, contract = asyncio.run(worker._compile_input(factory, lease))
    asyncio.run(worker._mark_compilation_running(factory, lease))
    for _ in range(2):
        asyncio.run(worker._record_compile_start(factory, lease, revision, contract))
    with pytest.raises(CompilerError, match="CALL_BUDGET_EXCEEDED"):
        asyncio.run(worker._record_compile_start(factory, lease, revision, contract))
    expire(pg_engine, lease)
    with pytest.raises(outbox.LeaseLost):
        asyncio.run(worker._record_compile_failure(factory, lease, revision, contract, CompilerError("MODEL_UNAVAILABLE")))
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.AIInteraction).where(m.AIInteraction.job_id==lease.id)) == 2
        assert c.scalar(select(m.Compilation.status).where(m.Compilation.job_id==lease.id)) == "running"


def test_completion_of_revised_brief_is_retained_as_stale(approval_workspace, pg_engine, monkeypatch):
    client, _, factory, session = approval_workspace
    compiler_double = worker.compile_revision
    brief = client.post("/api/briefs", json=brief_body(), headers=headers(session)).json()

    async def revise_while_compiling(contract, revision, **kwargs):
        result = await compiler_double(contract, revision, **kwargs)
        body = brief_body()
        body.pop("fixture_ref")
        body["expected_revision"] = 1
        revised = client.post(f"/api/briefs/{brief['id']}/revisions", json=body, headers=headers(session))
        assert revised.status_code == 201
        return result

    monkeypatch.setattr(worker, "compile_revision", revise_while_compiling)
    compilation = compile_brief(client, factory, session, brief)
    with pg_engine.connect() as c:
        row = c.execute(select(m.Compilation.__table__).where(m.Compilation.id==uuid.UUID(compilation["compilation_id"]))).mappings().one()
        assert row["status"] == "stale" and row["interaction_id"] is not None
        assert c.scalar(select(m.AIInteraction.validated).where(m.AIInteraction.id==row["interaction_id"])) is True
    response = client.post("/api/mandates", json={"task_id": brief["task_id"], "brief_revision_id": brief["revision_id"],
        "compilation_id": compilation["compilation_id"], "terms": brief["terms"]}, headers=headers(session))
    assert response.status_code == 409 and response.json()["code"] == "STALE_REVISION"


def test_nonpayment_history_stays_executor_owned_on_replacement(approval_workspace, pg_engine):
    client, ids, _, session = approval_workspace
    request = original_replacement(approval_workspace)
    with pg_engine.begin() as c:
        c.execute(update(m.PaymentAttempt).where(m.PaymentAttempt.id==ids["attempt"]).values(
            unresolved=False, nonpayment_confirmed=True, state="failed"))
        c.execute(update(m.PaymentObligation).where(m.PaymentObligation.id==ids["obligation"]).values(next_attempt_no=2))
        c.execute(update(m.DeliveryTask).where(m.DeliveryTask.id==ids["task"]).values(state="failed"))
    version = replacement(client, session, request, str(ids["mandate"]), str(ids["version"]))
    response = approve(client, session, version, str(ids["version"]))
    assert response.status_code == 200, response.text
    with pg_engine.connect() as c:
        assert c.scalar(select(m.DeliveryTask.state).where(m.DeliveryTask.id==ids["task"])) == "failed"
        assert c.scalar(select(m.DeliveryTask.hold_reasons).where(m.DeliveryTask.id==ids["task"])) == ["NEW_MANDATE_REQUIRES_DELIVERY"]
        assert c.scalar(select(m.PaymentObligation.next_attempt_no).where(m.PaymentObligation.id==ids["obligation"])) == 2


def test_approval_reloads_authority_changed_before_lock(approval_workspace, monkeypatch):
    client, _, _, session = approval_workspace
    _, _, request = compiled(approval_workspace)
    first = draft(client, session, request)
    second = replacement(client, session, request, first["mandate_id"], None)
    original_lock = commands.lock_workspace
    interleave = True

    async def concurrent_approval(db, agency_id, **kwargs):
        nonlocal interleave
        if interleave:
            interleave = False
            response = await asyncio.to_thread(approve, client, session, second)
            assert response.status_code == 200, response.text
        return await original_lock(db, agency_id, **kwargs)

    monkeypatch.setattr(commands, "lock_workspace", concurrent_approval)
    response = approve(client, session, first)
    assert response.status_code == 409 and response.json()["code"] == "STALE_MANDATE", response.text
    assert client.get(f"/api/mandates/{first['mandate_id']}").json()["current_version_id"] == second["id"]
