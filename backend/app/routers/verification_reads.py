import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.models import Agency, Brief, BriefRevision, Contractor, Delivery, DemoRun, EvidenceArtifact, EvidenceBundle, Mandate, MandateVersion, PaymentAttempt
from backend.app.schemas.verification import DeliveryResponse
from backend.app.services.auth import Actor, authorize_task, aware, get_actor, now
from backend.app.services.evidence_store import bundle_by_id, delivery_by_id, public_bundle, public_delivery, verify_bundle, visible_deliveries
from backend.app.services.pagination import decode_cursor, encode_cursor

router = APIRouter(tags=["Deliveries", "Evidence"])


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    task = await authorize_task(db, actor, task_id)
    brief = await db.get(Brief, task.brief_id)
    revision = await db.get(BriefRevision, brief.current_revision_id)
    mandate = await db.scalar(select(Mandate).where(Mandate.agency_id==actor.agency_id, Mandate.task_id==task.id))
    version = await db.get(MandateVersion, mandate.current_version_id) if mandate and mandate.current_version_id else None
    if revision is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Current brief revision is unavailable.")
    bound_revision = await db.get(BriefRevision, version.brief_revision_id) if version else revision
    contractor = await db.get(Contractor, version.contractor_id) if version else await db.scalar(select(Contractor).where(
        Contractor.agency_id==actor.agency_id, Contractor.recipient_ref==revision.proposed_terms.get("recipient_ref")))
    if bound_revision is None or contractor is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Task directory or brief configuration is unavailable.")
    attempt = await db.scalar(select(PaymentAttempt).where(PaymentAttempt.agency_id==actor.agency_id,
        PaymentAttempt.task_id==task.id).order_by(PaymentAttempt.attempt_no.desc()).limit(1))
    agency = await db.get(Agency, actor.agency_id)
    run = await db.get(DemoRun, task.demo_run_id)
    actions = []
    if (actor.role=="contractor" and version and version.lifecycle_state=="approved" and
        aware(version.expires_at)>now() and attempt is None and agency.current_demo_run_id==task.demo_run_id and run.state=="active"
        and task.state in {"awaiting_delivery", "verifying", "correction_requested", "evidence_passed"}):
        actions = ["submit_delivery"]
    amount = {"currency": "USD", "value": f"{version.amount_cents//100}.{version.amount_cents%100:02d}"} if version else revision.proposed_terms.get("amount")
    return {"id": task.id, "agency_id": actor.agency_id, "demo_run_id": task.demo_run_id, "is_featured_archive": False,
        "brief_id": brief.id, "title": revision.title, "family": bound_revision.family,
        "contractor": {"id": contractor.id, "recipient_ref": contractor.recipient_ref, "display_name": contractor.display_name, "environment": "sandbox"},
        "amount": amount, "state": task.state, "hold_reasons": task.hold_reasons, "review_required": task.review_required,
        "version": task.version, "mandate_version_id": version.id if version else None, "current_delivery_id": task.current_delivery_id,
        "current_bundle_id": task.current_bundle_id, "existing_attempt_id": attempt.id if attempt else None,
        "allowed_actions": actions, "updated_at": task.updated_at}


@router.get("/api/deliveries/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(delivery_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    return await public_delivery(db, actor, await delivery_by_id(db, actor, delivery_id))


@router.get("/api/tasks/{task_id}/deliveries")
async def list_deliveries(task_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db),
                          cursor: str | None = Query(default=None, max_length=256), limit: int = Query(default=50, ge=1, le=100)):
    await authorize_task(db, actor, task_id)
    query = visible_deliveries(actor).where(Delivery.task_id==task_id)
    if cursor:
        stamp, identifier = decode_cursor(cursor, actor.agency_id)
        query = query.where(or_(Delivery.created_at<stamp, and_(Delivery.created_at==stamp, Delivery.id<identifier)))
    rows = (await db.scalars(query.order_by(Delivery.created_at.desc(), Delivery.id.desc()).limit(limit+1))).all()
    following = encode_cursor(actor.agency_id, rows[limit-1].created_at, rows[limit-1].id) if len(rows)>limit else None
    return {"items": [await public_delivery(db, actor, r) for r in rows[:limit]], "next_cursor": following}


@router.get("/api/evidence/{bundle_id}")
async def get_bundle(bundle_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    return await public_bundle(db, actor, await bundle_by_id(db, actor, bundle_id))


@router.get("/api/tasks/{task_id}/evidence")
async def list_evidence(task_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db),
                        cursor: str | None = Query(default=None, max_length=256), limit: int = Query(default=50, ge=1, le=100)):
    await authorize_task(db, actor, task_id)
    allowed = visible_deliveries(actor).with_only_columns(Delivery.id)
    query = select(EvidenceBundle).where(EvidenceBundle.agency_id==actor.agency_id,
        EvidenceBundle.task_id==task_id, EvidenceBundle.delivery_id.in_(allowed))
    if cursor:
        stamp, identifier = decode_cursor(cursor, actor.agency_id)
        query = query.where(or_(EvidenceBundle.created_at<stamp, and_(EvidenceBundle.created_at==stamp, EvidenceBundle.id<identifier)))
    rows = (await db.scalars(query.order_by(EvidenceBundle.created_at.desc(), EvidenceBundle.id.desc()).limit(limit+1))).all()
    following = encode_cursor(actor.agency_id, rows[limit-1].created_at, rows[limit-1].id) if len(rows)>limit else None
    return {"items": [await public_bundle(db, actor, r) for r in rows[:limit]], "next_cursor": following}


@router.get("/api/evidence/artifacts/{artifact_id}")
async def get_artifact(artifact_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    artifact = await db.scalar(select(EvidenceArtifact).where(EvidenceArtifact.agency_id==actor.agency_id, EvidenceArtifact.id==artifact_id))
    if artifact is None:
        raise APIError(404, "NOT_FOUND", "Evidence artifact not found.")
    bundle = await bundle_by_id(db, actor, artifact.bundle_id)
    await verify_bundle(db, bundle)
    return Response(content=artifact.content, media_type=artifact.media_type,
        headers={"ETag": f'"{artifact.digest}"', "X-Content-SHA256": artifact.digest,
                 "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})
