import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import EvidenceBundle, EvidenceResult, EvidenceArtifact, AcceptanceCheck, Delivery
from backend.app.schemas.api_schemas import EvidenceBundleResponse, CheckObservation, EvidenceReviewResult
from backend.app.services.auth import Actor, authorize_task, get_actor

router = APIRouter(prefix="/api/v1/evidence", tags=["Evidence"])

@router.get("/{bundle_id}", response_model=EvidenceBundleResponse)
async def get_evidence_bundle(bundle_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    b_stmt = select(EvidenceBundle).where(EvidenceBundle.id == bundle_id, EvidenceBundle.agency_id == actor.agency_id)
    b_res = await db.execute(b_stmt)
    bundle = b_res.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Evidence bundle not found")
    await authorize_task(db, actor, bundle.task_id)

    r_stmt = select(EvidenceResult, AcceptanceCheck.check_id).join(
        AcceptanceCheck, AcceptanceCheck.id == EvidenceResult.acceptance_check_id
    ).where(EvidenceResult.bundle_id == bundle.id)
    r_res = await db.execute(r_stmt)
    results = [
        CheckObservation(check_id=check_id, outcome=er.outcome, observations=er.observations)
        for er, check_id in r_res.all()
    ]

    a_stmt = select(EvidenceArtifact.id).where(
        EvidenceArtifact.bundle_id == bundle.id,
        EvidenceArtifact.media_type == "image/png"
    )
    a_res = await db.execute(a_stmt)
    artifact_id = a_res.scalar_one_or_none()

    return EvidenceBundleResponse(
        id=bundle.id,
        task_id=bundle.task_id,
        delivery_id=bundle.delivery_id,
        bundle_digest=bundle.bundle_digest,
        results=results,
        screenshot_artifact_id=artifact_id,
        ai_review=None
    )

@router.get("/artifacts/{artifact_id}/bytes")
async def get_artifact_bytes(artifact_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    stmt = select(EvidenceArtifact).where(EvidenceArtifact.id == artifact_id, EvidenceArtifact.agency_id == actor.agency_id)
    res = await db.execute(stmt)
    artifact = res.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    bundle = await db.scalar(select(EvidenceBundle).where(EvidenceBundle.id==artifact.bundle_id, EvidenceBundle.agency_id==actor.agency_id))
    await authorize_task(db, actor, bundle.task_id)

    return Response(content=artifact.content, media_type=artifact.media_type)
