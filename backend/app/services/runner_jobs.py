"""Runner leases, immutable ingestion and current-pointer eligibility under one lock."""

import base64
import binascii
import hashlib
import io
import uuid
from datetime import timedelta

from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_, func, or_, select, update

from backend.app.config import settings
from backend.app.errors import APIError
from backend.app.models import Agency, AuditLog, BriefRevision, Delivery, DeliveryTask, DemoRun, EvidenceArtifact, EvidenceBundle, EvidenceResult, FixtureManifest, Mandate, MandateVersion, VerificationJob, AcceptanceCheck
from backend.app.schemas.verification import RunnerJob
from backend.app.services.auth import aware, now
from backend.app.services.catalog import validated_snapshot
from backend.app.services.commands import canonical_digest
from backend.app.services.locking import lock_workspace
from fixture_contract.observations import ObservationError, measured_outcome, provenance
from fixture_contract.registry import canonical_bytes


def lease_owned(job_id, agency_id, token):
    return (VerificationJob.id==job_id, VerificationJob.agency_id==agency_id,
            VerificationJob.state=="running", VerificationJob.lease_token==token,
            VerificationJob.lease_until > func.clock_timestamp())


def public_job(job):
    if canonical_digest(job.inputs) != job.input_digest:
        raise APIError(409, "INVALID_JOB", "Verification input digest does not match.")
    fields = {k: job.inputs[k] for k in ("task_id", "delivery_id", "mandate_version_id", "mandate_digest",
        "artifact_version_id", "artifact_digest", "fixture_url", "checks")}
    return RunnerJob(job_id=job.id, lease_token=job.lease_token, lease_until=job.lease_until, **fields).model_dump(mode="json")


async def claim(db, agency_id, body):
    await db.rollback()
    async with db.begin():
        # Serialize recovery/new claims for a worker without holding the lock during execution.
        await lock_workspace(db, agency_id)
        existing = await db.scalar(select(VerificationJob).where(VerificationJob.agency_id==agency_id,
            VerificationJob.state=="running", VerificationJob.worker_id==body.worker_id,
            VerificationJob.lease_until>func.clock_timestamp()).with_for_update())
        if existing is not None:
            return public_job(existing)
        eligible = or_(VerificationJob.state=="queued", and_(VerificationJob.state=="running",
            VerificationJob.lease_until<=func.clock_timestamp()))
        # Exhausted jobs are terminal, and never silently produce passing observations.
        exhausted = (await db.scalars(select(VerificationJob).where(VerificationJob.agency_id==agency_id,
            eligible, VerificationJob.lease_attempt>=settings.RUNNER_MAX_ATTEMPTS).with_for_update(skip_locked=True))).all()
        for job in exhausted:
            job.state, job.lease_token, job.lease_until, job.worker_id = "error", None, None, None
        job = await db.scalar(select(VerificationJob).where(VerificationJob.agency_id==agency_id,
            eligible, VerificationJob.lease_attempt<settings.RUNNER_MAX_ATTEMPTS)
            .order_by(VerificationJob.created_at, VerificationJob.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        job.state, job.worker_id, job.lease_token = "running", body.worker_id, uuid.uuid4()
        job.lease_attempt += 1
        job.started_at = now()
        job.lease_until = now()+timedelta(seconds=settings.RUNNER_LEASE_SECONDS)
        return public_job(job)


async def heartbeat(db, agency_id, job_id, body):
    await db.rollback()
    async with db.begin():
        changed = await db.scalar(update(VerificationJob).where(*lease_owned(job_id, agency_id, body.lease_token))
            .values(lease_until=func.clock_timestamp()+timedelta(seconds=settings.RUNNER_LEASE_SECONDS)).returning(VerificationJob.id))
        if changed is None:
            raise APIError(409, "LEASE_LOST", "Runner lease is no longer current.")


def png_bytes(upload):
    try:
        data = base64.b64decode(upload.data_base64, validate=True)
        if not data or len(data)>524288 or hashlib.sha256(data).hexdigest()!=upload.sha256:
            raise ValueError
        with Image.open(io.BytesIO(data)) as image:
            if image.format!="PNG" or image.size!=(320, 640):
                raise ValueError
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # Validate actual pixel decoding, rather than only a PNG signature.
        return data
    except (ValueError, OSError, binascii.Error, UnidentifiedImageError, Image.DecompressionBombError):
        raise APIError(422, "INVALID_EVIDENCE", "Screenshot bytes, digest or PNG decoding are invalid.") from None


def validate_upload(job, body, contract):
    if body.artifact_digest!=job.inputs["artifact_digest"] or body.mandate_digest!=job.inputs["mandate_digest"]:
        raise APIError(409, "INVALID_EVIDENCE", "Evidence digests do not match leased inputs.")
    if [r.check_id for r in body.results] != [c["check_id"] for c in job.inputs["checks"]]:
        raise APIError(422, "INVALID_EVIDENCE", "Exactly the three leased checks are required in order.")
    wire_job = public_job(job)
    screenshots = [png_bytes(s) for s in body.screenshots]
    used = set()
    for result, check in zip(body.results, job.inputs["checks"]):
        encoded = canonical_bytes(result.model_dump(mode="json"))
        if len(encoded)>65536 or len(canonical_bytes(result.observations))+1000>65536:
            raise APIError(422, "INVALID_EVIDENCE", "Structured result exceeds the size limit.")
        if not aware(job.started_at)-timedelta(seconds=5) <= result.completed_at <= now()+timedelta(seconds=5):
            raise APIError(422, "INVALID_EVIDENCE", "Observation timestamp is outside this lease run.")
        if set(result.observations)!={"provenance", "measurement"} or result.observations["provenance"]!=provenance(wire_job, check):
            raise APIError(422, "INVALID_EVIDENCE", "Result provenance does not match the leased run.")
        try:
            outcome = measured_outcome(check["template_type"], result.observations["measurement"], contract.facts)
        except (ObservationError, ValueError, TypeError):
            raise APIError(422, "INVALID_EVIDENCE", "Measurements do not match the trusted template.") from None
        if result.outcome != outcome:
            raise APIError(422, "INVALID_EVIDENCE", "Outcome contradicts recorded measurements.")
        indexes = result.screenshot_indexes
        if len(set(indexes))!=len(indexes) or any(i>=len(screenshots) or body.screenshots[i].check_id!=result.check_id for i in indexes):
            raise APIError(422, "INVALID_EVIDENCE", "Screenshot references do not match their checks.")
        if not check["template_type"].startswith("api_") and result.outcome!="error" and not indexes:
            raise APIError(422, "INVALID_EVIDENCE", "Browser measurements require an attributable screenshot.")
        used.update(indexes)
    if used != set(range(len(screenshots))):
        raise APIError(422, "INVALID_EVIDENCE", "Every screenshot must be referenced by its own check.")
    return screenshots


async def current_run(db, job):
    task = await db.scalar(select(DeliveryTask).where(DeliveryTask.agency_id==job.agency_id, DeliveryTask.id==job.task_id))
    mandate = await db.scalar(select(Mandate).where(Mandate.agency_id==job.agency_id, Mandate.task_id==job.task_id))
    version = await db.scalar(select(MandateVersion).where(MandateVersion.agency_id==job.agency_id,
        MandateVersion.id==uuid.UUID(job.inputs["mandate_version_id"])))
    active = await db.scalar(select(DemoRun.id).join(Agency, (Agency.id==DemoRun.agency_id)&(Agency.current_demo_run_id==DemoRun.id))
        .where(DemoRun.agency_id==job.agency_id, DemoRun.id==uuid.UUID(job.inputs["demo_run_id"]), DemoRun.state=="active"))
    eligible = (task is not None and mandate is not None and version is not None and active is not None
        and task.current_delivery_id==job.delivery_id and mandate.current_version_id==version.id
        and version.lifecycle_state=="approved" and aware(version.expires_at)>now()
        and version.payload_digest==job.inputs["mandate_digest"] and task.state=="verifying")
    return task, eligible


async def complete(db, agency_id, job_id, body, request_id):
    fingerprint = canonical_digest({k: v for k, v in body.model_dump(mode="json").items() if k!="lease_token"})
    await db.rollback()
    async with db.begin():
        task_id = await db.scalar(select(VerificationJob.task_id).where(VerificationJob.agency_id==agency_id, VerificationJob.id==job_id))
        if task_id is None:
            raise APIError(404, "NOT_FOUND", "Runner job not found.")
        await lock_workspace(db, agency_id, task_id=task_id)
        job = await db.scalar(select(VerificationJob).where(VerificationJob.agency_id==agency_id, VerificationJob.id==job_id).with_for_update())
        if job.completion_digest is not None:
            if job.lease_token!=body.lease_token or job.completion_digest!=fingerprint:
                raise APIError(409, "COMPLETION_CONFLICT", "This job already has different completion data or lease identity.")
            bundle = await db.scalar(select(EvidenceBundle).where(EvidenceBundle.agency_id==agency_id, EvidenceBundle.verification_job_id==job.id))
            return {"bundle_id": str(bundle.id), "state": "deduplicated"}
        if await db.scalar(select(VerificationJob.id).where(*lease_owned(job_id, agency_id, body.lease_token))) is None:
            raise APIError(409, "LEASE_LOST", "Runner lease is no longer current.")
        public_job(job)
        manifest = await db.scalar(select(FixtureManifest).where(FixtureManifest.agency_id==agency_id,
            FixtureManifest.id==uuid.UUID(job.inputs["manifest_id"])))
        if manifest is None or manifest.digest!=job.inputs["manifest_digest"]:
            raise APIError(409, "INVALID_JOB", "Trusted manifest does not match the run.")
        contract = validated_snapshot(manifest)
        screenshots = validate_upload(job, body, contract)
        checks = (await db.scalars(select(AcceptanceCheck).where(AcceptanceCheck.agency_id==agency_id,
            AcceptanceCheck.mandate_version_id==uuid.UUID(job.inputs["mandate_version_id"])).order_by(AcceptanceCheck.check_id))).all()
        if len(checks)!=3:
            raise APIError(409, "INVALID_JOB", "Approved check lineage is unavailable.")
        bundle_id = uuid.uuid4()
        artifacts, results = [], []
        for upload, data in zip(body.screenshots, screenshots):
            artifacts.append({"id": str(uuid.uuid4()), "check_id": upload.check_id, "media_type": "image/png",
                              "sha256": upload.sha256, "size_bytes": len(data)})
        for result, check in zip(body.results, checks):
            result_id, json_id = uuid.uuid4(), uuid.uuid4()
            result_data = result.model_dump(mode="json")
            encoded = canonical_bytes(result_data)
            artifacts.append({"id": str(json_id), "check_id": result.check_id, "media_type": "application/json",
                              "sha256": hashlib.sha256(encoded).hexdigest(), "size_bytes": len(encoded)})
            refs = [f"screenshot:{artifacts[i]['id']}" for i in result.screenshot_indexes]
            results.append({"id": str(result_id), "ref": f"result:{result_id}", "check_id": check.check_id,
                "type": check.template_type, "outcome": result.outcome, "observations": result.observations,
                "artifact_refs": refs, "completed_at": result_data["completed_at"],
                "result_digest": canonical_digest(result_data)})
        document = {"bundle_id": str(bundle_id), "run_id": str(job.id), "inputs": job.inputs,
                    "completion_digest": fingerprint, "results": results, "artifacts": artifacts}
        bundle = EvidenceBundle(id=bundle_id, agency_id=agency_id, task_id=job.task_id, delivery_id=job.delivery_id,
            mandate_version_id=uuid.UUID(job.inputs["mandate_version_id"]), verification_job_id=job.id,
            artifact_digest=body.artifact_digest, mandate_digest=body.mandate_digest, manifest_id=manifest.id,
            bundle_digest=canonical_digest(document), manifest_json=document)
        db.add(bundle)
        await db.flush()
        for metadata, data in zip(artifacts[:len(screenshots)], screenshots):
            db.add(EvidenceArtifact(id=uuid.UUID(metadata["id"]), agency_id=agency_id, bundle_id=bundle.id,
                check_id=metadata["check_id"], media_type=metadata["media_type"], digest=metadata["sha256"], content=data))
        for index, (result, check, metadata) in enumerate(zip(body.results, checks, results)):
            db.add(EvidenceResult(id=uuid.UUID(metadata["id"]), agency_id=agency_id, bundle_id=bundle.id,
                mandate_version_id=bundle.mandate_version_id, acceptance_check_id=check.id, outcome=result.outcome,
                observations=result.observations, result_digest=metadata["result_digest"], completed_at=result.completed_at))
            artifact_meta = artifacts[len(screenshots)+index]
            db.add(EvidenceArtifact(id=uuid.UUID(artifact_meta["id"]), agency_id=agency_id, bundle_id=bundle.id,
                check_id=result.check_id, media_type="application/json", digest=artifact_meta["sha256"],
                content=canonical_bytes(result.model_dump(mode="json"))))
        task, eligible = await current_run(db, job)
        if eligible:
            task.current_bundle_id = bundle.id
            task.review_required = True
            task.hold_reasons = ["REVIEW_NOT_IMPLEMENTED"]
            if any(r.outcome=="error" for r in body.results):
                task.hold_reasons.append("VERIFICATION_ERROR")
            elif any(r.outcome=="fail" for r in body.results):
                task.hold_reasons.append("CHECK_FAILED")
            task.version += 1
            task.updated_at = now()
        await db.flush()
        changed = await db.scalar(update(VerificationJob).where(*lease_owned(job_id, agency_id, body.lease_token)).values(
            state="completed" if eligible else "stale", completed_at=func.clock_timestamp(),
            completion_digest=fingerprint, lease_until=None).returning(VerificationJob.id))
        if changed is None:
            raise APIError(409, "LEASE_LOST", "Runner lease expired before completion commit.")
        db.add(AuditLog(agency_id=agency_id, service_actor="trusted_runner", event_type="verification.completed",
            correlation_id=request_id, references_json={"job_id": str(job.id), "bundle_id": str(bundle.id)},
            details={"bundle_digest": bundle.bundle_digest, "eligible": eligible}))
        return {"bundle_id": str(bundle.id), "state": "accepted" if eligible else "stale"}
