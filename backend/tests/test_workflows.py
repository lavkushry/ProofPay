"""Real PostgreSQL/HTTP acceptance; fixture graph and stage output are explicit doubles."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app import models as m
from backend.app.config import settings
from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.main import app
from backend.app.services import commands, outbox
from backend.app.services.auth import COOKIE, Actor
from backend.app.services.compiler import CompileResult
from backend.tests.postgres_support import PASSWORDS, database_factory, graph, pg_engine, postgres_url
from backend import worker
from backend.worker import process_lease
from fixture_contract.registry import load_contract

pytestmark = pytest.mark.postgres


@pytest.fixture
def workspace(graph, pg_engine, postgres_url, monkeypatch):
    with pg_engine.begin() as c:
        # Other relational test graphs do not participate in this worker queue.
        c.execute(text("UPDATE outbox_events SET state='held', lease_token=NULL, lease_until=NULL WHERE state IN ('ready','leased')"))
        for name, role in (("maya", "contractor"), ("leo", "contractor"), ("judge", "judge")):
            graph[name] = uuid.uuid4()
            c.execute(m.User.__table__.insert().values(id=graph[name], agency_id=graph["agency"], role=role, display_name=name))
        c.execute(update(m.Contractor).where(m.Contractor.id==graph["contractor"]).values(user_id=graph["maya"]))
        c.execute(m.Contractor.__table__.insert().values(id=uuid.uuid4(), agency_id=graph["agency"], user_id=graph["leo"], recipient_ref="contractor_leo", display_name="Leo"))
        c.execute(update(m.Agency).where(m.Agency.id==graph["agency"]).values(current_demo_run_id=graph["run"]))
        c.execute(update(m.Brief).where(m.Brief.id==graph["brief"]).values(current_revision_id=graph["revision"]))
        c.execute(update(m.Mandate).where(m.Mandate.id==graph["mandate"]).values(current_version_id=graph["version"]))
        c.execute(update(m.DeliveryTask).where(m.DeliveryTask.id==graph["task"]).values(current_bundle_id=graph["bundle"]))
    monkeypatch.setattr(settings, "DEFAULT_AGENCY_ID", graph["agency"])
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "SESSION_CSRF_KEY", SecretStr("test-only-hmac-key-with-at-least-32-bytes"))
    for field, value in (("DEMO_JUDGE_ACCESS_CODE", "judge-code"), ("DEMO_OWNER_ACCESS_CODE", "owner-code"),
                         ("DEMO_MAYA_ACCESS_CODE", "maya-code"), ("DEMO_LEO_ACCESS_CODE", "leo-code")):
        monkeypatch.setattr(settings, field, SecretStr(value))
    api_url = postgres_url.set(drivername="postgresql+asyncpg", username="proofpay_api", password=PASSWORDS["proofpay_api"])
    engine = create_async_engine(api_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def database():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            yield client, graph, factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def login(client, persona="owner", code="judge-code"):
    response = client.post("/api/session", json={"access_code": code, "persona": persona})
    assert response.status_code == 201, response.text
    return response.json()


def headers(session, key=None):
    return {"X-CSRF-Token": session["csrf_token"], "Idempotency-Key": str(key or uuid.uuid4())}


def brief_body():
    return {"title": "Capture a draft", "text": "Fix checkout viewport without changing totals.",
            "family": "responsive_css", "fixture_ref": "checkout_fixture", "terms": {
                "recipient_ref": "contractor_maya", "amount": {"currency": "USD", "value": "75.00"},
                "principal_cap": {"currency": "USD", "value": "225.00"}, "max_attempts": 3,
                "expires_at": "2030-01-01T00:00:00Z"}}


def count(c, model, agency):
    return c.scalar(select(func.count()).select_from(model).where(model.agency_id==agency))


def test_codes_cookie_rotation_revocation_and_audit(workspace, pg_engine):
    client, ids, _ = workspace
    assert client.get("/api/session").status_code == 401
    bad = client.post("/api/session", json={"access_code": "sensitive-rejected-code", "persona": "owner"})
    assert bad.status_code == 401 and "sensitive-rejected-code" not in bad.text
    assert client.post("/api/session", json={"access_code": "maya-code", "persona": "owner"}).status_code == 403
    session = login(client)
    cookie = client.cookies.get(COOKIE)
    assert session["principal_id"] == str(ids["judge"]) and session["effective_user_id"] == str(ids["owner"])
    assert session["is_judge"] and session["role"] == "owner"
    assert client.post("/api/judge/role", json={"persona": "contractor_maya"}).status_code == 403
    assert client.post("/api/judge/role", headers={**headers(session), "Origin": "https://foreign.invalid"}, json={"persona": "contractor_maya"}).status_code == 403
    rotated = client.post("/api/judge/role", headers=headers(session), json={"persona": "contractor_maya"})
    assert rotated.status_code == 200
    maya = rotated.json()
    assert maya["principal_id"] == session["principal_id"] and maya["effective_user_id"] == str(ids["maya"])
    assert maya["csrf_token"] != session["csrf_token"] and client.cookies.get(COOKIE) != cookie
    assert client.get("/api/session", headers={"Cookie": f"{COOKIE}={cookie}"}).status_code == 401
    assert client.delete("/api/session", headers={"X-CSRF-Token": session["csrf_token"]}).status_code == 403
    assert client.delete("/api/session", headers=headers(maya)).status_code == 204
    assert client.get("/api/session").status_code == 401
    with pg_engine.connect() as c:
        sessions = c.execute(select(m.SessionModel.__table__).where(m.SessionModel.agency_id==ids["agency"])).mappings().all()
        assert all(s["revoked_at"] for s in sessions)
        assert sessions[0]["cookie_hash"] == hashlib.sha256(cookie.encode()).hexdigest()
        audits = c.execute(select(m.AuditLog.__table__).where(m.AuditLog.agency_id==ids["agency"])).mappings().all()
        assert {a["event_type"] for a in audits} == {"session.created", "session.persona_changed", "session.revoked"}
        assert all(a["principal_user_id"] == ids["judge"] for a in audits)
        public = json.dumps([dict(a) for a in audits], default=str)
        assert cookie not in public and "judge-code" not in public and session["csrf_token"] not in public


def test_secure_cookie_expiry_and_invalid_configuration(workspace, pg_engine, monkeypatch):
    client, ids, _ = workspace
    session = login(client, code="owner-code")
    assert not session["is_judge"]
    assert client.post("/api/judge/role", headers=headers(session), json={"persona": "contractor_leo"}).status_code == 403
    with pg_engine.begin() as c:
        c.execute(update(m.SessionModel).where(m.SessionModel.agency_id==ids["agency"]).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
    assert client.get("/api/session").status_code == 401
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", True)
    response = client.post("/api/session", json={"access_code": "owner-code", "persona": "owner"})
    assert "Secure" in response.headers["set-cookie"] and "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    monkeypatch.setattr(settings, "SESSION_CSRF_KEY", SecretStr(""))
    assert client.post("/api/session", json={"access_code": "owner-code", "persona": "owner"}).status_code == 503


def test_contractor_scope_and_read_guards(workspace):
    client, ids, _ = workspace
    login(client, "contractor_maya", "maya-code")
    assert [t["id"] for t in client.get("/api/v1/tasks").json()] == [str(ids["task"])]
    for path in (f"/api/v1/tasks/{ids['task']}", f"/api/v1/mandates/{ids['task']}",
                 f"/api/v1/evidence/{ids['bundle']}", f"/api/v1/receipts/{ids['task']}", f"/api/jobs/{ids['job']}"):
        assert client.get(path).status_code == 200, path
    login(client, "contractor_leo", "leo-code")
    assert client.get("/api/v1/tasks").json() == []
    for path in (f"/api/v1/tasks/{ids['task']}", f"/api/v1/mandates/{ids['task']}",
                 f"/api/v1/evidence/{ids['bundle']}", f"/api/v1/receipts/{ids['task']}", f"/api/jobs/{ids['job']}"):
        assert client.get(path).status_code == 404, path
    assert client.get("/api/v1/catalog/recipients").status_code == 403


def test_capture_replay_conflict_and_atomic_records(workspace, pg_engine):
    client, ids, _ = workspace
    session = login(client, code="owner-code")
    key = uuid.uuid4()
    assert client.post("/api/briefs", json=brief_body()).status_code == 403
    assert client.post("/api/briefs", json=brief_body(), headers={"X-CSRF-Token": session["csrf_token"]}).status_code == 400
    first = client.post("/api/briefs", json=brief_body(), headers=headers(session, key))
    assert first.status_code == 201, first.text
    assert first.headers["cache-control"] == "no-store"
    replay = client.post("/api/briefs", json=brief_body(), headers=headers(session, key))
    assert replay.status_code == 201 and replay.json() == first.json()
    changed = {**brief_body(), "title": "Changed request"}
    conflict = client.post("/api/briefs", json=changed, headers=headers(session, key))
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    with pg_engine.connect() as c:
        assert count(c, m.Brief, ids["agency"]) == 2
        assert count(c, m.CommandReceipt, ids["agency"]) == 1
        assert count(c, m.OutboxEvent, ids["agency"]) == 2
        assert count(c, m.MandateVersion, ids["agency"]) == 1  # Draft grants no approval.
        audit = c.execute(select(m.AuditLog.__table__).where(m.AuditLog.event_type=="command.create_brief", m.AuditLog.agency_id==ids["agency"])).mappings().one()
        assert audit["effective_user_id"] == ids["owner"]
        job = c.execute(select(m.OutboxEvent.__table__).where(m.OutboxEvent.task_id==uuid.UUID(first.json()["task_id"]))).mappings().one()
    public_job = client.get(f"/api/jobs/{job['id']}")
    assert public_job.status_code == 200 and "payload" not in public_job.json() and "lease_token" not in public_job.json()


def test_validation_and_identity_scoped_receipts(workspace, pg_engine):
    client, ids, _ = workspace
    owner = login(client, code="owner-code")
    for terms in ({"amount": {"currency": "USD", "value": "0.00"}},
                  {"amount": {"currency": "USD", "value": "75.001"}},
                  {"amount": {"currency": "EUR", "value": "75.00"}},
                  {"principal_cap": {"currency": "USD", "value": "1.00"}},
                  {"max_attempts": True}, {"max_attempts": 4}, {"expires_at": 123}, {"expires_at": "2030-01-01T00:00:00"}):
        body = brief_body()
        body["terms"].update(terms)
        response = client.post("/api/briefs", json=body, headers=headers(owner))
        assert response.status_code == 422 and response.json()["code"] == "INVALID_REQUEST"
        assert "input" not in response.json()
    key = uuid.uuid4()
    first = client.post("/api/briefs", json=brief_body(), headers=headers(owner, key))
    judge = login(client)
    second = client.post("/api/briefs", json=brief_body(), headers=headers(judge, key))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]  # Same effective owner, distinct original principal.
    maya = login(client, "contractor_maya", "maya-code")
    assert client.post("/api/briefs", json=brief_body(), headers=headers(maya, key)).status_code == 403
    with pg_engine.connect() as c:
        assert count(c, m.CommandReceipt, ids["agency"]) == 2
        assert count(c, m.Brief, ids["agency"]) == 3


def test_foreign_agency_resources_are_hidden(workspace, pg_engine):
    client, _, _ = workspace
    foreign = {name: uuid.uuid4() for name in ("agency", "owner", "run", "brief", "task", "job")}
    with pg_engine.begin() as c:
        c.execute(m.Agency.__table__.insert().values(id=foreign["agency"], name="Foreign test workspace", advisory_lock_key=foreign["agency"].int % 2**62, principal_limit_cents=10000))
        c.execute(m.User.__table__.insert().values(id=foreign["owner"], agency_id=foreign["agency"], role="owner", display_name="Foreign owner"))
        c.execute(m.DemoRun.__table__.insert().values(id=foreign["run"], agency_id=foreign["agency"]))
        c.execute(m.Brief.__table__.insert().values(id=foreign["brief"], agency_id=foreign["agency"], created_by=foreign["owner"]))
        c.execute(m.DeliveryTask.__table__.insert().values(id=foreign["task"], agency_id=foreign["agency"], demo_run_id=foreign["run"], brief_id=foreign["brief"]))
        c.execute(m.OutboxEvent.__table__.insert().values(id=foreign["job"], agency_id=foreign["agency"], task_id=foreign["task"], state="held", event_type="test_double", dedup_key="foreign", payload={}))
    login(client, code="owner-code")
    for path in (f"/api/v1/tasks/{foreign['task']}", f"/api/v1/receipts/{foreign['task']}", f"/api/jobs/{foreign['job']}"):
        assert client.get(path).status_code == 404


def test_concurrent_capture_and_workspace_dispatch_lock(workspace, pg_engine):
    client, ids, _ = workspace
    session = login(client)
    with pg_engine.begin() as c:
        lock_key = c.scalar(select(m.Agency.advisory_lock_key).where(m.Agency.id==ids["agency"]))
        c.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        response = client.post("/api/briefs", json=brief_body(), headers=headers(session))
        assert response.status_code == 409 and response.json()["code"] == "WORKSPACE_BUSY"
    key, cookie = uuid.uuid4(), client.cookies.get(COOKIE)
    def capture():
        with TestClient(app) as independent:
            return independent.post("/api/briefs", json=brief_body(), headers={**headers(session, key), "Cookie": f"{COOKIE}={cookie}"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: capture(), range(2)))
    assert all(r.status_code in {201, 409} for r in results)
    successes = [r.json() for r in results if r.status_code == 201]
    assert successes and all(body == successes[0] for body in successes)
    assert capture().json() == successes[0]
    with pg_engine.connect() as c:
        assert count(c, m.CommandReceipt, ids["agency"]) == 1
        assert count(c, m.Brief, ids["agency"]) == 2


def test_command_rollback_and_alias_reauthorization(workspace, pg_engine):
    client, ids, factory = workspace
    session = login(client, "contractor_maya", "maya-code")
    cookie = client.cookies.get(COOKIE)
    with pg_engine.connect() as c:
        session_id = c.scalar(select(m.SessionModel.id).where(m.SessionModel.cookie_hash==hashlib.sha256(cookie.encode()).hexdigest()))
    actor = Actor(session_id, ids["agency"], ids["maya"], ids["maya"], "contractor", "contractor_maya", False)
    key = uuid.uuid4()
    body = {"task_id": str(ids["task"]), "artifact_version_id": str(ids["artifact"]),
            "mandate_version_id": str(ids["version"]), "expected_task_version": 1, "claim": "Explicit test double"}
    async def authorize(db, current):
        from backend.app.services.auth import authorize_task
        await authorize_task(db, current, ids["task"])
    async def mutate(db, current):
        return commands.CommandResult(202, {"job_id": str(ids["job"])}, ids["task"], "test_double", {})
    async def invoke(callback, command_key):
        async with factory() as db:
            return await commands.execute_command(db, actor, "submit_delivery", command_key, body, uuid.uuid4(), authorize, callback, task_id=ids["task"])
    async def broken(db, current):
        db.add(m.OutboxEvent(agency_id=ids["agency"], task_id=ids["task"], event_type="rollback_double", dedup_key=str(uuid.uuid4()), payload={}))
        await db.flush()
        raise APIError(503, "TEST_FAILURE", "Explicit rollback double")
    with pytest.raises(APIError):
        asyncio.run(invoke(broken, uuid.uuid4()))
    asyncio.run(invoke(mutate, key))
    for path in (f"/api/tasks/{ids['task']}/deliveries", f"/api/contractor/tasks/{ids['task']}/deliveries"):
        response = client.post(path, json={k:v for k,v in body.items() if k != "task_id"}, headers=headers(session, key))
        assert response.status_code == 202 and response.json() == {"job_id": str(ids["job"])}
    with pg_engine.begin() as c:
        assert count(c, m.OutboxEvent, ids["agency"]) == 2  # One original and one command; rollback added none.
        c.execute(update(m.Mandate).where(m.Mandate.id==ids["mandate"]).values(current_version_id=None))
    assert client.post(f"/api/tasks/{ids['task']}/deliveries", json={k:v for k,v in body.items() if k != "task_id"}, headers=headers(session, key)).status_code == 404


def test_final_receipt_race_rolls_back_loser(workspace, pg_engine, monkeypatch):
    client, ids, factory = workspace
    login(client, code="owner-code")
    with pg_engine.connect() as c:
        session_id = c.scalar(select(m.SessionModel.id).where(m.SessionModel.agency_id==ids["agency"]))
    actor = Actor(session_id, ids["agency"], ids["owner"], ids["owner"], "owner", None, False)
    key = uuid.uuid4()
    async def race():
        arrived = 0
        both = asyncio.Event()
        async def bypass_lock(*args, **kwargs):
            pass  # Explicit fault injection: exercise the final unique gate independently.
        monkeypatch.setattr(commands, "lock_workspace", bypass_lock)
        async def authorize(*args):
            pass
        async def mutate(db, current):
            nonlocal arrived
            identifier = uuid.uuid4()
            db.add(m.Brief(id=identifier, agency_id=ids["agency"], created_by=ids["owner"]))
            await db.flush()
            arrived += 1
            if arrived == 2:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=5)
            return commands.CommandResult(201, {"id": str(identifier)}, None, "test_double", {})
        async def invoke():
            async with factory() as db:
                return await commands.execute_command(db, actor, "create_brief", key, {}, uuid.uuid4(), authorize, mutate)
        return await asyncio.gather(invoke(), invoke())
    results = asyncio.run(race())
    assert results[0] == results[1]
    with pg_engine.connect() as c:
        assert count(c, m.Brief, ids["agency"]) == 2
        assert count(c, m.CommandReceipt, ids["agency"]) == 1
        assert count(c, m.OutboxEvent, ids["agency"]) == 2
        assert count(c, m.AuditLog, ids["agency"]) == 2  # Session creation plus winning command.


def add_job(pg_engine, ids, *, payload=None, event_type="test_double"):
    identifier = uuid.uuid4()
    with pg_engine.begin() as c:
        c.execute(m.OutboxEvent.__table__.insert().values(id=identifier, agency_id=ids["agency"], task_id=ids["task"],
                  event_type=event_type, dedup_key=str(identifier), payload=payload or {}))
    return identifier


def expire(pg_engine, lease):
    with pg_engine.begin() as c:
        c.execute(update(m.OutboxEvent).where(m.OutboxEvent.id==lease.id).values(lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)))


def test_claim_skip_locked_heartbeat_and_reclaim_fencing(workspace, pg_engine):
    _, ids, factory = workspace
    first = add_job(pg_engine, ids)
    second = add_job(pg_engine, ids)
    with pg_engine.begin() as c:
        c.execute(select(m.OutboxEvent.id).where(m.OutboxEvent.id==first).with_for_update())
        lease = asyncio.run(outbox.claim(factory))
        assert lease.id == second
    leases = asyncio.run(outbox.claim(factory))
    assert leases.id == first
    asyncio.run(outbox.heartbeat(factory, leases))
    expire(pg_engine, leases)
    for operation in (outbox.heartbeat(factory, leases), outbox.store_stage_output(factory, leases, "check", {}), outbox.fail(factory, leases, "OLD")):
        with pytest.raises(outbox.LeaseLost):
            asyncio.run(operation)
    new = asyncio.run(outbox.claim(factory))
    assert new.id == first and new.token != leases.token and new.attempt == 2
    with pytest.raises(outbox.LeaseLost):
        asyncio.run(outbox.heartbeat(factory, leases))


def test_crash_stage_cache_completion_and_immutable_output(workspace, pg_engine):
    _, ids, factory = workspace
    identifier = add_job(pg_engine, ids, payload={"brief_id": str(ids["brief"]), "revision_id": str(ids["revision"]),
        "actor": {"principal_id": str(ids["judge"]), "effective_user_id": str(ids["owner"])}}, event_type="brief_recorded")
    lease = asyncio.run(outbox.claim(factory))
    output = {"brief_id": str(ids["brief"])}
    asyncio.run(outbox.store_stage_output(factory, lease, "capture", output))
    with pytest.raises(outbox.StageConflict):
        asyncio.run(outbox.store_stage_output(factory, lease, "capture", {"brief_id": "replacement"}))
    # Simulated crash: process disappears after the accepted output transaction.
    expire(pg_engine, lease)
    redelivery = asyncio.run(outbox.claim(factory))
    assert redelivery.stage_state["capture"]["output"] == output
    asyncio.run(process_lease(factory, redelivery))
    with pg_engine.connect() as c:
        job = c.execute(select(m.OutboxEvent.__table__).where(m.OutboxEvent.id==identifier)).mappings().one()
        assert job["state"] == "done" and job["lease_token"] is None
        assert job["stage_state"]["result"]["resource_id"] == str(ids["brief"])
        assert c.scalar(select(m.AuditLog.principal_user_id).where(m.AuditLog.correlation_id==identifier)) == ids["judge"]
    with pytest.raises(outbox.LeaseLost):
        asyncio.run(outbox.complete(factory, lease, lambda *_: None))
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError), pg_engine.begin() as c:
        c.execute(update(m.OutboxEvent).where(m.OutboxEvent.id==identifier).values(payload={"replaced": True}))


def test_completion_expiry_rolls_back_domain_and_audit(workspace, pg_engine):
    _, ids, factory = workspace
    identifier = add_job(pg_engine, ids)
    lease = asyncio.run(outbox.claim(factory, lease_seconds=1))
    async def late(db, job):
        task = await db.get(m.DeliveryTask, ids["task"])
        task.state = "verifying"
        await db.execute(text("SELECT pg_sleep(1.1)"))
        return {"resource_id": str(ids["task"])}
    with pytest.raises(outbox.LeaseLost):
        asyncio.run(outbox.complete(factory, lease, late))
    with pg_engine.connect() as c:
        assert c.scalar(select(m.DeliveryTask.state).where(m.DeliveryTask.id==ids["task"])) == "brief_captured"
        assert c.scalar(select(m.AuditLog.id).where(m.AuditLog.correlation_id==identifier)) is None


def test_bounded_redelivery_and_unsupported_jobs_hold(workspace, pg_engine):
    _, ids, factory = workspace
    identifier = add_job(pg_engine, ids)
    for number in range(1, 4):
        lease = asyncio.run(outbox.claim(factory, max_attempts=3))
        assert lease.id == identifier and lease.attempt == number
        expire(pg_engine, lease)
    assert asyncio.run(outbox.claim(factory, max_attempts=3)) is None
    with pg_engine.connect() as c:
        job = c.execute(select(m.OutboxEvent.__table__).where(m.OutboxEvent.id==identifier)).mappings().one()
        assert job["state"] == "failed" and job["last_error_code"] == "RETRY_EXHAUSTED"
    other = add_job(pg_engine, ids, event_type="release_payment")
    lease = asyncio.run(outbox.claim(factory))
    asyncio.run(process_lease(factory, lease))
    with pg_engine.connect() as c:
        assert c.scalar(select(m.OutboxEvent.state).where(m.OutboxEvent.id==other)) == "held"


def test_sigkill_redelivery_preserves_accepted_stage(workspace, pg_engine, tmp_path):
    _, ids, factory = workspace
    identifier = add_job(pg_engine, ids, payload={"brief_id": str(ids["brief"]), "revision_id": str(ids["revision"])}, event_type="brief_recorded")
    marker = tmp_path / "accepted.json"
    # A real separate worker process commits an accepted stage, then is killed.
    script = """
import asyncio, json, sys
from pathlib import Path
from backend.app.database import AsyncSessionLocal
from backend.app.services import outbox
async def main():
    lease = await outbox.claim(AsyncSessionLocal, lease_seconds=1)
    await outbox.store_stage_output(AsyncSessionLocal, lease, 'capture', {'brief_id': lease.payload['brief_id']})
    Path(sys.argv[1]).write_text(json.dumps({'id': str(lease.id), 'token': str(lease.token)}))
    await asyncio.sleep(60)
asyncio.run(main())
"""
    environment = {**os.environ, "DATABASE_URL": factory.kw["bind"].url.render_as_string(hide_password=False)}
    process = subprocess.Popen([sys.executable, "-c", script, str(marker)], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.05)
        assert marker.exists(), "Child worker did not persist its stage"
        accepted = json.loads(marker.read_text())
        process.kill()
        process.wait(timeout=5)
        assert process.returncode == -9 and accepted["id"] == str(identifier)
        time.sleep(1.1)  # Real database lease expiry, without editing the lease timestamp.
        recovered = asyncio.run(outbox.claim(factory))
        assert str(recovered.token) != accepted["token"] and recovered.attempt == 2
        assert recovered.stage_state["capture"]["output"] == {"brief_id": str(ids["brief"])}
        asyncio.run(process_lease(factory, recovered))
        with pg_engine.connect() as c:
            assert c.scalar(select(m.OutboxEvent.state).where(m.OutboxEvent.id==identifier)) == "done"
            assert c.scalar(select(func.count()).select_from(m.AuditLog).where(m.AuditLog.correlation_id==identifier)) == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_compile_command_enqueues_and_persists_validated_interaction(workspace, pg_engine, monkeypatch):
    client, ids, factory = workspace
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("test-openai-key"))
    session = login(client, code="owner-code")
    key = uuid.uuid4()
    captured = client.post("/api/briefs", json=brief_body(), headers=headers(session, uuid.uuid4()))
    assert captured.status_code == 201, captured.text
    brief = captured.json()
    request = {"expected_revision": brief["revision"], "expected_digest": brief["digest"]}
    response = client.post(f"/api/briefs/{brief['id']}/compile", json=request, headers=headers(session, key))
    assert response.status_code == 202, response.text
    assert client.post(f"/api/briefs/{brief['id']}/compile", json=request, headers=headers(session, key)).json() == response.json()

    contract = load_contract()
    family = contract.family("responsive_css")
    proposal = {"checks": [{"check_id": f"C0{number}", "template_type": item.template_type,
                             "params": item.params, "compiled_by": "ai", "approved": False}
                for number, item in enumerate(family.templates, start=1)],
                "ambiguities": [], "clarifying_questions": []}
    from backend.app.schemas.api_schemas import CheckProposal
    async def fake_compile(_contract, _revision, **_kwargs):
        return CompileResult(CheckProposal.model_validate(proposal), "ready", "openai", "test-model",
                             "compiler-v0.1", "proofpay-tools-v0.1", "b"*64, "c"*64, {"total_tokens": 1})
    monkeypatch.setattr(worker, "compile_revision", fake_compile)
    with pg_engine.connect() as connection:
        jobs = connection.execute(select(m.OutboxEvent.id, m.OutboxEvent.payload).where(
            m.OutboxEvent.event_type=="compile_requested")).all()
        job_id = next(identifier for identifier, payload in jobs if payload["brief_id"] == brief["id"])
        connection.execute(update(m.OutboxEvent).where(m.OutboxEvent.event_type=="brief_recorded",
                         m.OutboxEvent.state=="ready").values(state="held"))
        connection.commit()
    lease = asyncio.run(outbox.claim(factory))
    assert lease.id == job_id
    asyncio.run(worker.process_lease(factory, lease))
    with pg_engine.connect() as connection:
        compilation = connection.execute(select(m.Compilation.__table__).where(m.Compilation.job_id==job_id)).mappings().one()
        interactions = connection.execute(select(m.AIInteraction.__table__).where(m.AIInteraction.job_id==job_id)).mappings().all()
        assert compilation["status"] == "ready" and any(item["validated"] for item in interactions)
        assert any(item["error_code"] == "STARTED" for item in interactions)
        assert connection.scalar(select(m.OutboxEvent.state).where(m.OutboxEvent.id==job_id)) == "done"
    projection = client.get(f"/api/briefs/{brief['id']}/compilation")
    assert projection.status_code == 200 and projection.json()["status"] == "ready"
