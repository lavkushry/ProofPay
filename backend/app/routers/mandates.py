import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import Mandate, MandateVersion, AcceptanceCheck, DeliveryTask, utc_now
from backend.app.schemas.api_schemas import MandateApprovalRequest, MandateResponse, CheckItem

router = APIRouter(prefix="/api/v1/mandates", tags=["Mandates"])

@router.get("/{task_id}", response_model=MandateResponse)
async def get_mandate_by_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Mandate).where(Mandate.task_id == task_id)
    res = await db.execute(stmt)
    mandate = res.scalar_one_or_none()
    if not mandate or not mandate.current_version_id:
        raise HTTPException(status_code=404, detail="Mandate not found")

    v_stmt = select(MandateVersion).where(MandateVersion.id == mandate.current_version_id)
    v_res = await db.execute(v_stmt)
    version = v_res.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Mandate version not found")

    c_stmt = select(AcceptanceCheck).where(AcceptanceCheck.mandate_version_id == version.id)
    c_res = await db.execute(c_stmt)
    checks = c_res.scalars().all()

    return MandateResponse(
        id=mandate.id,
        task_id=version.task_id,
        version=version.version,
        lifecycle_state=version.lifecycle_state,
        amount_cents=version.amount_cents,
        currency=version.currency,
        checks=[
            CheckItem(
                check_id=c.check_id,
                template_type=c.template_type,
                params=c.params,
                compiled_by=c.compiled_by,
                approved=c.approved
            ) for c in checks
        ],
        payload_digest=version.payload_digest,
        approved_at=version.approved_at
    )

@router.post("/approve", response_model=MandateResponse)
async def approve_mandate(req: MandateApprovalRequest, db: AsyncSession = Depends(get_db)):
    """
    Approves and freezes mandate payload (Invariant I2).
    Transitions task state to 'awaiting_delivery'.
    """
    v_stmt = select(MandateVersion).where(MandateVersion.id == req.mandate_version_id)
    v_res = await db.execute(v_stmt)
    version = v_res.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Mandate version not found")

    if version.lifecycle_state == "approved":
        # Idempotent response
        pass
    else:
        version.lifecycle_state = "approved"
        version.approved_at = utc_now()
        version.approved_by = version.agency_id

        # Update checks
        c_stmt = select(AcceptanceCheck).where(AcceptanceCheck.mandate_version_id == version.id)
        c_res = await db.execute(c_stmt)
        for check in c_res.scalars().all():
            check.approved = True

        # Transition task to awaiting_delivery
        t_stmt = select(DeliveryTask).where(DeliveryTask.id == version.task_id)
        t_res = await db.execute(t_stmt)
        task = t_res.scalar_one_or_none()
        if task:
            task.state = "awaiting_delivery"

        await db.commit()

    return await get_mandate_by_task(version.task_id, db)
