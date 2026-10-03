"""Immutable delivery capture and trusted job inputs; external execution is leased."""

import uuid
from urllib.parse import urlsplit

from sqlalchemy import func, select

from backend.app.config import settings
from backend.app.errors import APIError
from backend.app.models import AcceptanceCheck, ArtifactVersion, BriefRevision, Contractor, Delivery, Mandate, MandateVersion, PaymentAttempt, VerificationJob
from backend.app.schemas.verification import DeliveryResponse
from backend.app.services.auth import aware, now
from backend.app.services.catalog import validated_snapshot
from backend.app.services.commands import CommandResult, canonical_digest
from backend.app.services.mandates import active_obligation
from backend.app.models import FixtureManifest
from fixture_contract.registry import canonical_bytes


def fixture_base():
    parts = urlsplit(settings.FIXTURE_URL)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Trusted fixture origin is invalid.")
    return settings.FIXTURE_URL.rstrip("/")


async def capture(db, actor, task, body):
    if actor.role != "contractor":
        raise APIError(403, "FORBIDDEN", "Only the assigned contractor may submit delivery.")
    if task.version != body.expected_task_version:
        raise APIError(409, "STALE_TASK", "Task changed; reload before submitting.")
    await active_obligation(db, actor, task)
    attempt = await db.scalar(select(PaymentAttempt.id).where(PaymentAttempt.agency_id==actor.agency_id,
                                                               PaymentAttempt.task_id==task.id))
    if attempt is not None:
        raise APIError(409, "PAYMENT_ALREADY_INITIATED", "Delivery cannot be replaced after payment initiation.")
    mandate = await db.scalar(select(Mandate).where(Mandate.agency_id==actor.agency_id, Mandate.task_id==task.id))
    version = await db.scalar(select(MandateVersion).join(Contractor,
        (Contractor.agency_id==MandateVersion.agency_id)&(Contractor.id==MandateVersion.contractor_id))
        .where(MandateVersion.agency_id==actor.agency_id, MandateVersion.task_id==task.id,
               MandateVersion.id==body.mandate_version_id, Contractor.user_id==actor.effective_user_id))
    if (version is None or mandate is None or mandate.current_version_id != version.id or
        version.lifecycle_state != "approved" or aware(version.expires_at) <= now()):
        raise APIError(409, "STALE_MANDATE", "Delivery requires current, unexpired approved authority.")
    if task.state not in {"awaiting_delivery", "verifying", "correction_requested", "evidence_passed"}:
        raise APIError(409, "STALE_TASK", "Task is not accepting deliveries.")
    if canonical_digest(version.public_payload) != version.payload_digest:
        raise APIError(409, "STALE_MANDATE", "Approved snapshot integrity is invalid.")
    revision = await db.scalar(select(BriefRevision).where(BriefRevision.agency_id==actor.agency_id,
                                                          BriefRevision.id==version.brief_revision_id))
    if revision is None:
        raise APIError(409, "STALE_MANDATE", "Approved revision lineage is unavailable.")
    manifest = await db.scalar(select(FixtureManifest).where(FixtureManifest.agency_id==actor.agency_id,
                                                            FixtureManifest.id==revision.manifest_id))
    if manifest is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Trusted fixture manifest is unavailable.")
    contract = validated_snapshot(manifest)
    artifact = await db.scalar(select(ArtifactVersion).where(ArtifactVersion.agency_id==actor.agency_id,
        ArtifactVersion.id==body.artifact_version_id, ArtifactVersion.manifest_id==manifest.id,
        ArtifactVersion.family==revision.family))
    trusted = contract.artifact(artifact.artifact_ref) if artifact else None
    if trusted is None or artifact.digest != trusted.digest or artifact.relative_path != trusted.relative_path:
        raise APIError(409, "INVALID_ARTIFACT", "Artifact must belong to the mandate's reviewed family and manifest.")
    records = (await db.scalars(select(AcceptanceCheck).where(AcceptanceCheck.agency_id==actor.agency_id,
        AcceptanceCheck.mandate_version_id==version.id).order_by(AcceptanceCheck.check_id))).all()
    checks = [{"check_id": c.check_id, "template_type": c.template_type, "params": c.params,
               "compiled_by": c.compiled_by, "approved": c.approved} for c in records]
    expected = [{"check_id": f"C0{i}", "template_type": t.template_type, "params": t.params,
                 "compiled_by": "ai", "approved": True} for i, t in enumerate(contract.family(revision.family).templates, 1)]
    if canonical_bytes(checks) != canonical_bytes(expected) or checks != version.public_payload.get("acceptance_checks"):
        raise APIError(409, "STALE_MANDATE", "Approved checks do not match the trusted templates.")
    delivery_id, job_id, stamp = uuid.uuid4(), uuid.uuid4(), now()
    sequence = (await db.scalar(select(func.max(Delivery.sequence)).where(
        Delivery.agency_id==actor.agency_id, Delivery.task_id==task.id)) or 0) + 1
    delivery = Delivery(id=delivery_id, agency_id=actor.agency_id, task_id=task.id, mandate_version_id=version.id,
        artifact_version_id=artifact.id, artifact_digest=artifact.digest, mandate_digest=version.payload_digest,
        submitted_by=actor.effective_user_id, claim=body.claim, claim_digest=canonical_digest(body.claim),
        sequence=sequence, previous_delivery_id=task.current_delivery_id, created_at=stamp)
    db.add(delivery)
    await db.flush()
    inputs = {"task_id": str(task.id), "demo_run_id": str(task.demo_run_id), "delivery_id": str(delivery.id),
        "mandate_version_id": str(version.id), "mandate_digest": version.payload_digest,
        "artifact_version_id": str(artifact.id), "artifact_digest": artifact.digest,
        "manifest_id": str(manifest.id), "manifest_digest": manifest.digest,
        "fixture_url": fixture_base()+artifact.relative_path, "checks": checks}
    db.add(VerificationJob(id=job_id, agency_id=actor.agency_id, task_id=task.id, delivery_id=delivery.id,
                           inputs=inputs, input_digest=canonical_digest(inputs)))
    task.current_delivery_id, task.current_bundle_id = delivery.id, None
    task.state, task.review_required, task.hold_reasons = "verifying", False, []
    task.version += 1
    task.updated_at = stamp
    result = DeliveryResponse(id=delivery.id, task_id=task.id, mandate_version_id=version.id,
        artifact_version_id=artifact.id, artifact_digest=artifact.digest, claim=body.claim,
        claim_ref=f"claim:{delivery.id}", sequence=sequence, previous_delivery_id=delivery.previous_delivery_id,
        is_current=True, verification_job_id=job_id, created_at=stamp).model_dump(mode="json")
    return CommandResult(201, result, task.id, "delivery_recorded",
                         {"delivery_id": str(delivery.id), "verification_job_id": str(job_id)})
