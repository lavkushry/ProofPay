"""Real PostgreSQL/HTTP leases and ingestion; measurements/PNG here are explicit doubles."""

import asyncio
import base64
import copy
import hashlib
import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from backend.app import models as m
from backend.app.config import settings
from backend.app.services import outbox, runner_jobs
from backend.tests.postgres_support import database_factory, graph, pg_engine, postgres_url
from backend.tests.test_workflows import headers, login, workspace
from backend.tests.test_mandates import approval_workspace, approve, compiled, draft, replacement
from fixture_contract.observations import provenance
from fixture_contract.registry import load_contract

pytestmark = pytest.mark.postgres
RUNNER_TOKEN = "explicit-test-only-runner-service-token"


@pytest.fixture
def verification_workspace(approval_workspace, pg_engine, monkeypatch):
    client, ids, factory, owner = approval_workspace
    contract = load_contract()
    with pg_engine.begin() as c:
        c.execute(update(m.VerificationJob).where(m.VerificationJob.id==ids["verification"]).values(state="error"))
        for artifact in contract.artifacts:
            c.execute(m.ArtifactVersion.__table__.insert().values(id=uuid.uuid4(), agency_id=ids["agency"],
                manifest_id=ids["manifest"], artifact_ref=artifact.artifact_ref, family=artifact.family,
                digest=artifact.digest, relative_path=artifact.relative_path))
    monkeypatch.setattr(settings, "RUNNER_SERVICE_TOKEN", SecretStr(RUNNER_TOKEN))
    return approval_workspace


def runner_headers():
    return {"Authorization": f"Bearer {RUNNER_TOKEN}"}


def approved_task(verification_workspace, family="responsive_css"):
    client, ids, factory, owner = verification_workspace
    brief, compilation, request = compiled(verification_workspace, family)
    version = draft(client, owner, request)
    result = approve(client, owner, version)
    assert result.status_code==200, result.text
    return brief, result.json(), request


def submit(verification_workspace, pg_engine, brief, version, reference="checkout_mobile_fixed", session=None, key=None):
    client, ids, _, _ = verification_workspace
    session = session or login(client, "contractor_maya", "maya-code")
    with pg_engine.connect() as c:
        artifact_id = c.scalar(select(m.ArtifactVersion.id).where(m.ArtifactVersion.agency_id==ids["agency"], m.ArtifactVersion.artifact_ref==reference))
    task = client.get(f"/api/tasks/{brief['task_id']}")
    assert task.status_code==200, task.text
    body = {"artifact_version_id": str(artifact_id), "mandate_version_id": version["id"],
            "expected_task_version": task.json()["version"], "claim": "Explicit measurement double"}
    response = client.post(f"/api/tasks/{brief['task_id']}/deliveries", json=body, headers=headers(session, key))
    assert response.status_code==201, response.text
    return response.json(), body, session


def claim(client, worker="test-runner"):
    response = client.post("/internal/runner/jobs/claim", json={"worker_id": worker}, headers=runner_headers())
    assert response.status_code==200, response.text
    return response.json()


def completion_double(job):
    stream = io.BytesIO()
    Image.new("RGB", (320, 640), (20, 100, 200)).save(stream, format="PNG")
    data = stream.getvalue()
    screenshots, results = [], []
    measurements = [
        {"viewport_width": 320, "scroll_width": 320, "overflow_px": 0},
        {"total_cents": 4200, "currency": "USD", "baseline_total_cents": 4200},
        {"control_ref": "checkout_pay", "reached": True, "tabs": 1, "focused_id": "checkout_pay"},
    ]
    for i, (check, measurement) in enumerate(zip(job["checks"], measurements)):
        screenshots.append({"check_id": check["check_id"], "media_type": "image/png", "sha256": hashlib.sha256(data).hexdigest(), "data_base64": base64.b64encode(data).decode()})
        results.append({"check_id": check["check_id"], "outcome": "pass", "observations": {
            "provenance": provenance(job, check), "measurement": measurement}, "screenshot_indexes": [i],
            "completed_at": datetime.now(timezone.utc).isoformat()})
    return {"lease_token": job["lease_token"], "artifact_digest": job["artifact_digest"], "mandate_digest": job["mandate_digest"],
            "results": results, "screenshots": screenshots}


def complete(client, job, body):
    return client.post(f"/internal/runner/jobs/{job['job_id']}/complete", json=body, headers=runner_headers())


def test_delivery_alias_replay_and_latest_selection(verification_workspace, pg_engine):
    client, ids, factory, owner = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    key = uuid.uuid4()
    first, body, maya = submit(verification_workspace, pg_engine, brief, version, key=key)
    alias = client.post(f"/api/contractor/tasks/{brief['task_id']}/deliveries", json=body, headers=headers(maya, key))
    assert alias.status_code==201 and alias.json()==first
    changed = client.post(f"/api/tasks/{brief['task_id']}/deliveries", json={**body, "claim": "Changed claim"}, headers=headers(maya, key))
    assert changed.status_code==409 and changed.json()["code"]=="IDEMPOTENCY_CONFLICT"
    second, _, _ = submit(verification_workspace, pg_engine, brief, version, "checkout_mobile_broken", session=maya)
    assert second["sequence"]==2 and second["previous_delivery_id"]==first["id"]
    assert client.get(f"/api/deliveries/{first['id']}").json()["is_current"] is False
    history = client.get(f"/api/tasks/{brief['task_id']}/deliveries?limit=1").json()
    assert history["items"][0]["id"]==second["id"] and history["next_cursor"]
    assert client.get(f"/api/tasks/{brief['task_id']}/deliveries", params={"cursor": history["next_cursor"]}).json()["items"][0]["id"]==first["id"]
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.PaymentObligation).where(m.PaymentObligation.task_id==uuid.UUID(brief["task_id"])))==1
    login(client, code="owner-code")
    assert client.post(f"/api/tasks/{brief['task_id']}/deliveries", json=body, headers=headers(login(client, code="owner-code"))).status_code==403
    login(client, "contractor_leo", "leo-code")
    assert client.get(f"/api/deliveries/{first['id']}").status_code==404
    # Capture events only record lineage; actual execution belongs to runner leases.
    while (lease := asyncio.run(outbox.claim(factory))) is not None:
        from backend.worker import process_lease
        asyncio.run(process_lease(factory, lease))


@pytest.mark.parametrize("invalid", ["stale_task", "foreign_artifact", "wrong_family", "expired", "paid_history"])
def test_delivery_rejects_invalid_authority_and_financial_history(verification_workspace, pg_engine, invalid):
    client, ids, _, owner = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    maya = login(client, "contractor_maya", "maya-code")
    with pg_engine.connect() as c:
        artifact = c.scalar(select(m.ArtifactVersion.id).where(m.ArtifactVersion.agency_id==ids["agency"], m.ArtifactVersion.artifact_ref==("checkout_api_fixed" if invalid=="wrong_family" else "checkout_mobile_fixed")))
    body = {"artifact_version_id": str(artifact), "mandate_version_id": version["id"], "expected_task_version": 2, "claim": "No authority"}
    if invalid=="stale_task":
        body["expected_task_version"] = 1
    elif invalid=="foreign_artifact":
        body["artifact_version_id"] = str(ids["artifact"])
    elif invalid=="expired":
        from sqlalchemy import text
        with pg_engine.begin() as c:
            c.execute(text("UPDATE mandate_versions SET lifecycle_state='expired' WHERE id=:id"), {"id": uuid.UUID(version["id"])})
    elif invalid=="paid_history":
        with pg_engine.begin() as c:
            c.execute(update(m.DeliveryTask).where(m.DeliveryTask.id==uuid.UUID(brief["task_id"])).values(state="paid"))
    response = client.post(f"/api/tasks/{brief['task_id']}/deliveries", json=body, headers=headers(maya))
    assert response.status_code==409, response.text
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.Delivery).where(m.Delivery.task_id==uuid.UUID(brief["task_id"])))==0


def test_runner_audience_recovery_heartbeat_and_lease_loss(verification_workspace, pg_engine):
    client, ids, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    delivery, _, _ = submit(verification_workspace, pg_engine, brief, version)
    assert client.post("/internal/runner/jobs/claim", json={"worker_id": "test"}).status_code==401
    job = claim(client)
    assert job["job_id"]==delivery["verification_job_id"]
    assert claim(client)==job
    assert client.post("/internal/runner/jobs/claim", json={"worker_id": "other"}, headers=runner_headers()).status_code==204
    assert client.post(f"/internal/runner/jobs/{job['job_id']}/heartbeat", json={"lease_token": str(uuid.uuid4())}, headers=runner_headers()).status_code==409
    assert client.post(f"/internal/runner/jobs/{job['job_id']}/heartbeat", json={"lease_token": job["lease_token"]}, headers=runner_headers()).status_code==204
    with pg_engine.begin() as c:
        c.execute(update(m.VerificationJob).where(m.VerificationJob.id==uuid.UUID(job["job_id"])).values(lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)))
    assert complete(client, job, completion_double(job)).status_code==409
    recovered = claim(client, "other")
    assert recovered["job_id"]==job["job_id"] and recovered["lease_token"]!=job["lease_token"]
    client.cookies.clear()
    assert client.get(f"/api/tasks/{brief['task_id']}", headers=runner_headers()).status_code==401


def test_completion_immutable_replay_readback_and_review_hold(verification_workspace, pg_engine):
    client, ids, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    body = completion_double(job)
    response = complete(client, job, body)
    assert response.status_code==200 and response.json()["state"]=="accepted", response.text
    bundle_id = response.json()["bundle_id"]
    assert complete(client, job, body).json()=={"bundle_id": bundle_id, "state": "deduplicated"}
    conflict = copy.deepcopy(body)
    conflict["results"][0]["completed_at"] = datetime.now(timezone.utc).isoformat()
    assert complete(client, job, conflict).json()["code"]=="COMPLETION_CONFLICT"
    bundle = client.get(f"/api/evidence/{bundle_id}")
    assert bundle.status_code==200, bundle.text
    public = bundle.json()
    assert len(public["results"])==3 and len(public["artifacts"])==6 and public["run_id"]==job["job_id"]
    assert public["is_current"] is True and public["review"] is None
    for artifact in public["artifacts"]:
        downloaded = client.get(artifact["download_path"])
        assert downloaded.status_code==200
        assert hashlib.sha256(downloaded.content).hexdigest()==artifact["sha256"]==downloaded.headers["x-content-sha256"]
    task = client.get(f"/api/tasks/{brief['task_id']}").json()
    assert task["state"]=="verifying" and task["review_required"] and task["hold_reasons"]==["REVIEW_NOT_IMPLEMENTED"]
    assert client.get(f"/api/jobs/{job['job_id']}").json()["result_resource_id"]==bundle_id
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.PaymentAttempt).where(m.PaymentAttempt.task_id==uuid.UUID(brief["task_id"])))==0
    for model, values, identifier in [(m.VerificationJob, {"inputs": {}}, uuid.UUID(job["job_id"])),
                                      (m.EvidenceBundle, {"manifest_json": {}}, uuid.UUID(bundle_id))]:
        with pytest.raises(IntegrityError), pg_engine.begin() as c:
            c.execute(update(model).where(model.id==identifier).values(**values))
    login(client, "contractor_leo", "leo-code")
    assert client.get(f"/api/evidence/{bundle_id}").status_code==404
    assert client.get(public["artifacts"][0]["download_path"]).status_code==404


@pytest.mark.parametrize("tamper", ["digest", "provenance", "duplicate", "outcome", "params", "png_hash", "png_decode", "png_dimensions", "screenshot_ref", "missing_screenshot", "timestamp", "oversize"])
def test_tampered_completion_cannot_persist_evidence(verification_workspace, pg_engine, tamper):
    client, _, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    body = completion_double(job)
    if tamper=="digest":
        body["artifact_digest"] = "a"*64
    elif tamper=="provenance":
        body["results"][0]["observations"]["provenance"]["run_id"] = str(uuid.uuid4())
    elif tamper=="duplicate":
        body["results"][1]["check_id"] = "C01"
    elif tamper=="outcome":
        body["results"][0]["observations"]["measurement"].update(scroll_width=480, overflow_px=160)
    elif tamper=="params":
        body["results"][0]["observations"]["measurement"]["viewport_width"] = 480
    elif tamper=="png_hash":
        body["screenshots"][0]["sha256"] = "a"*64
    elif tamper=="png_decode":
        data = b"\x89PNG\r\n\x1a\nnot-a-decoded-image"
        body["screenshots"][0].update(sha256=hashlib.sha256(data).hexdigest(), data_base64=base64.b64encode(data).decode())
    elif tamper=="png_dimensions":
        stream = io.BytesIO()
        Image.new("RGB", (20, 20)).save(stream, format="PNG")
        data = stream.getvalue()
        body["screenshots"][0].update(sha256=hashlib.sha256(data).hexdigest(), data_base64=base64.b64encode(data).decode())
    elif tamper=="screenshot_ref":
        body["results"][0]["screenshot_indexes"] = [2]
    elif tamper=="missing_screenshot":
        body["results"][0]["screenshot_indexes"] = []
    elif tamper=="timestamp":
        body["results"][0]["completed_at"] = "2001-01-01T00:00:00Z"
    elif tamper=="oversize":
        body["results"][0]["observations"]["large"] = "x"*65536
    response = complete(client, job, body)
    assert response.status_code in {409, 422}, response.text
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.EvidenceBundle).where(m.EvidenceBundle.verification_job_id==uuid.UUID(job["job_id"])))==0


@pytest.mark.parametrize("supersede", [False, True])
def test_stale_completion_keeps_history_without_current_evidence(verification_workspace, pg_engine, supersede):
    client, _, _, owner = verification_workspace
    brief, version, request = approved_task(verification_workspace)
    first, _, maya = submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    if supersede:
        owner = login(client)
        newer = replacement(client, owner, request, version["mandate_id"], version["id"])
        assert approve(client, owner, newer, version["id"]).status_code==200
        login(client, "contractor_maya", "maya-code")
    else:
        submit(verification_workspace, pg_engine, brief, version, "checkout_mobile_broken", session=maya)
    response = complete(client, job, completion_double(job))
    assert response.status_code==200 and response.json()["state"]=="stale", response.text
    bundle = client.get(f"/api/evidence/{response.json()['bundle_id']}")
    assert bundle.status_code==200 and bundle.json()["is_current"] is False
    assert client.get(f"/api/tasks/{brief['task_id']}").json()["current_bundle_id"] is None


def test_concurrent_completion_has_one_bundle(verification_workspace, pg_engine):
    client, _, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    body = completion_double(job)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: complete(client, job, body), range(2)))
    assert any(r.status_code==200 for r in responses)
    for r in responses:
        assert r.status_code in {200, 409}, r.text
    assert complete(client, job, body).status_code==200
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.EvidenceBundle).where(m.EvidenceBundle.verification_job_id==uuid.UUID(job["job_id"])))==1


def test_lease_expiring_during_ingestion_rolls_back_all_evidence(verification_workspace, pg_engine, monkeypatch):
    client, _, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    body = completion_double(job)
    with pg_engine.begin() as c:
        c.execute(update(m.VerificationJob).where(m.VerificationJob.id==uuid.UUID(job["job_id"])).values(
            lease_until=datetime.now(timezone.utc)+timedelta(seconds=1)))
    original = runner_jobs.validate_upload

    def slow_decode(*args):
        decoded = original(*args)
        time.sleep(1.1)  # Actual wall time advances after initial ownership validation.
        return decoded

    monkeypatch.setattr(runner_jobs, "validate_upload", slow_decode)
    response = complete(client, job, body)
    assert response.status_code==409 and response.json()["code"]=="LEASE_LOST", response.text
    with pg_engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(m.EvidenceBundle).where(m.EvidenceBundle.verification_job_id==uuid.UUID(job["job_id"])))==0
        assert c.scalar(select(m.DeliveryTask.current_bundle_id).where(m.DeliveryTask.id==uuid.UUID(brief["task_id"]))) is None
        assert c.scalar(select(m.VerificationJob.completion_digest).where(m.VerificationJob.id==uuid.UUID(job["job_id"]))) is None


def test_exhausted_runner_lease_is_visible_without_evidence(verification_workspace, pg_engine):
    client, _, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    with pg_engine.begin() as c:
        c.execute(update(m.VerificationJob).where(m.VerificationJob.id==uuid.UUID(job["job_id"])).values(
            lease_attempt=settings.RUNNER_MAX_ATTEMPTS, lease_until=datetime.now(timezone.utc)-timedelta(seconds=1)))
    assert client.post("/internal/runner/jobs/claim", json={"worker_id": "recovery"}, headers=runner_headers()).status_code==204
    status = client.get(f"/api/jobs/{job['job_id']}").json()
    assert status["state"]=="failed" and status["result_resource_id"] is None
    assert status["hold_reasons"]==["RUNNER_RETRY_EXHAUSTED"]
    assert complete(client, job, completion_double(job)).json()["code"]=="LEASE_LOST"


def test_corrupt_stored_bytes_are_rejected_on_readback(verification_workspace, pg_engine):
    client, _, _, _ = verification_workspace
    brief, version, _ = approved_task(verification_workspace)
    submit(verification_workspace, pg_engine, brief, version)
    job = claim(client)
    bundle_id = complete(client, job, completion_double(job)).json()["bundle_id"]
    public = client.get(f"/api/evidence/{bundle_id}").json()
    artifact = next(a for a in public["artifacts"] if a["media_type"]=="image/png")
    # The table-owning test role injects corruption; the API role cannot bypass immutability.
    with pg_engine.begin() as c:
        c.exec_driver_sql("ALTER TABLE evidence_artifacts DISABLE TRIGGER USER")
        c.execute(update(m.EvidenceArtifact).where(m.EvidenceArtifact.id==uuid.UUID(artifact["id"])).values(content=b"corrupt"))
        c.exec_driver_sql("ALTER TABLE evidence_artifacts ENABLE TRIGGER USER")
    for path in (f"/api/evidence/{bundle_id}", artifact["download_path"]):
        response = client.get(path)
        assert response.status_code==409 and response.json()["code"]=="EVIDENCE_INTEGRITY_FAILED", response.text
