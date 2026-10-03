import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.models import EvidenceBundle, OutboxEvent, VerificationJob
from backend.app.services.auth import Actor, authorize_task, get_actor

router = APIRouter(tags=["Jobs"])


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    job = await db.scalar(select(OutboxEvent).where(OutboxEvent.id==job_id, OutboxEvent.agency_id==actor.agency_id))
    if job is None:
        verification = await db.scalar(select(VerificationJob).where(VerificationJob.id==job_id, VerificationJob.agency_id==actor.agency_id))
        if verification is None:
            raise APIError(404, "NOT_FOUND", "Job not found.")
        await authorize_task(db, actor, verification.task_id)
        bundle_id = await db.scalar(select(EvidenceBundle.id).where(EvidenceBundle.agency_id==actor.agency_id,
            EvidenceBundle.verification_job_id==verification.id))
        states = {"queued": "ready", "running": "leased", "completed": "done", "stale": "held", "error": "failed"}
        return {"id": verification.id, "type": "verification", "state": states[verification.state],
            "task_id": verification.task_id, "result_resource_id": bundle_id,
            "hold_reasons": ["STALE_EVIDENCE"] if verification.state=="stale" else ["RUNNER_RETRY_EXHAUSTED"] if verification.state=="error" else [],
            "created_at": verification.created_at, "updated_at": verification.completed_at or verification.started_at or verification.created_at}
    if job.task_id is not None:
        await authorize_task(db, actor, job.task_id)
    elif actor.role != "owner":
        raise APIError(404, "NOT_FOUND", "Job not found.")
    result = job.stage_state.get("result", {})
    return {"id": job.id, "type": job.event_type, "state": job.state, "task_id": job.task_id,
            "result_resource_id": result.get("resource_id"),
            "hold_reasons": [job.last_error_code] if job.last_error_code else [],
            "created_at": job.created_at, "updated_at": job.updated_at}
