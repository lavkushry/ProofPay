"""Read-back verification of immutable bundle manifests, rows and exact artifact bytes."""

import hashlib
import uuid

from sqlalchemy import select

from backend.app.errors import APIError
from backend.app.models import AcceptanceCheck, Agency, Contractor, Delivery, DeliveryTask, EvidenceArtifact, EvidenceBundle, EvidenceResult, Mandate, MandateVersion, VerificationJob
from backend.app.schemas.verification import RunnerResultUpload
from backend.app.services.commands import canonical_digest
from fixture_contract.registry import decode_json


def visible_deliveries(actor):
    query = select(Delivery).where(Delivery.agency_id==actor.agency_id)
    if actor.role=="contractor":
        query = query.join(MandateVersion, (MandateVersion.agency_id==Delivery.agency_id)&
            (MandateVersion.id==Delivery.mandate_version_id)).join(Contractor,
            (Contractor.agency_id==MandateVersion.agency_id)&(Contractor.id==MandateVersion.contractor_id))
        query = query.where(Contractor.user_id==actor.effective_user_id, MandateVersion.approved_at.is_not(None))
    elif actor.role!="owner":
        raise APIError(403, "FORBIDDEN", "An owner or contractor persona is required.")
    return query


async def delivery_by_id(db, actor, identifier):
    delivery = await db.scalar(visible_deliveries(actor).where(Delivery.id==identifier))
    if delivery is None:
        raise APIError(404, "NOT_FOUND", "Delivery not found.")
    return delivery


async def public_delivery(db, actor, delivery):
    task = await db.scalar(select(DeliveryTask).where(DeliveryTask.agency_id==actor.agency_id, DeliveryTask.id==delivery.task_id))
    job_id = await db.scalar(select(VerificationJob.id).where(VerificationJob.agency_id==actor.agency_id,
        VerificationJob.delivery_id==delivery.id).order_by(VerificationJob.created_at).limit(1))
    return {"id": delivery.id, "task_id": delivery.task_id, "mandate_version_id": delivery.mandate_version_id,
            "artifact_version_id": delivery.artifact_version_id, "artifact_digest": delivery.artifact_digest,
            "claim": delivery.claim, "claim_ref": f"claim:{delivery.id}", "sequence": delivery.sequence,
            "previous_delivery_id": delivery.previous_delivery_id, "is_current": task.current_delivery_id==delivery.id,
            "verification_job_id": job_id, "created_at": delivery.created_at}


async def bundle_by_id(db, actor, identifier):
    bundle = await db.scalar(select(EvidenceBundle).where(EvidenceBundle.agency_id==actor.agency_id, EvidenceBundle.id==identifier))
    if bundle is None:
        raise APIError(404, "NOT_FOUND", "Evidence bundle not found.")
    await delivery_by_id(db, actor, bundle.delivery_id)
    return bundle


def invalid():
    return APIError(409, "EVIDENCE_INTEGRITY_FAILED", "Stored evidence does not match its immutable manifest.")


async def verify_bundle(db, bundle):
    document = bundle.manifest_json
    if not document or canonical_digest(document)!=bundle.bundle_digest:
        raise invalid()
    job = await db.scalar(select(VerificationJob).where(VerificationJob.agency_id==bundle.agency_id,
                                                       VerificationJob.id==bundle.verification_job_id))
    delivery = await db.scalar(select(Delivery).where(Delivery.agency_id==bundle.agency_id, Delivery.id==bundle.delivery_id))
    if (job is None or delivery is None or document.get("bundle_id")!=str(bundle.id) or
        document.get("run_id")!=str(job.id) or document.get("inputs")!=job.inputs or
        document.get("completion_digest")!=job.completion_digest or canonical_digest(job.inputs)!=job.input_digest or
        job.inputs["task_id"]!=str(bundle.task_id) or job.inputs["delivery_id"]!=str(bundle.delivery_id) or
        job.inputs["mandate_version_id"]!=str(bundle.mandate_version_id) or job.inputs["manifest_id"]!=str(bundle.manifest_id) or
        job.inputs["artifact_digest"]!=bundle.artifact_digest or job.inputs["mandate_digest"]!=bundle.mandate_digest or
        delivery.artifact_digest!=bundle.artifact_digest or delivery.mandate_digest!=bundle.mandate_digest or
        canonical_digest(delivery.claim)!=delivery.claim_digest):
        raise invalid()
    artifacts = (await db.scalars(select(EvidenceArtifact).where(EvidenceArtifact.agency_id==bundle.agency_id,
                                                               EvidenceArtifact.bundle_id==bundle.id))).all()
    metadata = {m["id"]: m for m in document["artifacts"]}
    if set(metadata)!={str(a.id) for a in artifacts}:
        raise invalid()
    uploads = {}
    for artifact in artifacts:
        expected = metadata[str(artifact.id)]
        if (artifact.media_type!=expected["media_type"] or artifact.check_id!=expected["check_id"] or
            len(artifact.content)!=expected["size_bytes"] or artifact.digest!=expected["sha256"] or
            hashlib.sha256(artifact.content).hexdigest()!=artifact.digest):
            raise invalid()
        if artifact.media_type=="application/json":
            try:
                result = RunnerResultUpload.model_validate(decode_json(artifact.content))
                uploads[result.check_id] = result
            except (ValueError, TypeError):
                raise invalid() from None
    rows = (await db.execute(select(EvidenceResult, AcceptanceCheck).join(AcceptanceCheck,
        (AcceptanceCheck.agency_id==EvidenceResult.agency_id)&(AcceptanceCheck.id==EvidenceResult.acceptance_check_id))
        .where(EvidenceResult.agency_id==bundle.agency_id, EvidenceResult.bundle_id==bundle.id))).all()
    expected_results = {r["id"]: r for r in document["results"]}
    if len(rows)!=3 or set(expected_results)!={str(r.id) for r, _ in rows} or len(uploads)!=3:
        raise invalid()
    for result, check in rows:
        expected = expected_results[str(result.id)]
        upload = uploads.get(check.check_id)
        if (upload is None or result.mandate_version_id!=bundle.mandate_version_id or
            check.mandate_version_id!=bundle.mandate_version_id or expected["check_id"]!=check.check_id or
            expected["type"]!=check.template_type or expected["outcome"]!=result.outcome or
            expected["observations"]!=result.observations or upload.outcome!=result.outcome or
            upload.observations!=result.observations or upload.completed_at!=result.completed_at or
            canonical_digest(upload.model_dump(mode="json"))!=result.result_digest or
            expected["result_digest"]!=result.result_digest):
            raise invalid()
    return document, delivery, artifacts


async def public_bundle(db, actor, bundle):
    document, delivery, artifacts = await verify_bundle(db, bundle)
    task = await db.scalar(select(DeliveryTask).where(DeliveryTask.agency_id==actor.agency_id, DeliveryTask.id==bundle.task_id))
    mandate = await db.scalar(select(Mandate).where(Mandate.agency_id==actor.agency_id, Mandate.task_id==bundle.task_id))
    agency = await db.get(Agency, actor.agency_id)
    current = (task.current_bundle_id==bundle.id and task.current_delivery_id==bundle.delivery_id and
               mandate.current_version_id==bundle.mandate_version_id and agency.current_demo_run_id==task.demo_run_id)
    return {"id": str(bundle.id), "task_id": str(bundle.task_id), "delivery_id": str(bundle.delivery_id),
        "mandate_version_id": str(bundle.mandate_version_id), "mandate_digest": bundle.mandate_digest,
        "artifact_digest": bundle.artifact_digest, "run_id": str(bundle.verification_job_id), "digest": bundle.bundle_digest,
        "claim_ref": f"claim:{delivery.id}", "manifest_ref": f"manifest:{bundle.id}",
        "results": [{k: v for k, v in r.items() if k!="result_digest"} for r in document["results"]],
        "artifacts": [{"id": str(a.id), "ref": f"screenshot:{a.id}" if a.media_type=="image/png" else None,
            "check_id": a.check_id, "media_type": a.media_type, "sha256": a.digest, "size_bytes": len(a.content),
            "download_path": f"/api/evidence/artifacts/{a.id}"} for a in sorted(artifacts, key=lambda a: str(a.id))],
        "review": None, "review_interaction_id": None, "is_current": current, "created_at": bundle.created_at}
