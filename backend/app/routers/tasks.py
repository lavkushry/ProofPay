import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import DeliveryTask, Brief, BriefRevision, Mandate, MandateVersion
from backend.app.schemas.api_schemas import DeliveryTaskResponse
from backend.app.config import settings

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])

@router.get("", response_model=List[DeliveryTaskResponse])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DeliveryTask, BriefRevision.title, MandateVersion.amount_cents)
        .join(Brief, Brief.id == DeliveryTask.brief_id)
        .outerjoin(BriefRevision, BriefRevision.id == Brief.current_revision_id)
        .outerjoin(Mandate, Mandate.task_id == DeliveryTask.id)
        .outerjoin(MandateVersion, MandateVersion.id == Mandate.current_version_id)
        .where(DeliveryTask.agency_id == settings.DEFAULT_AGENCY_ID)
        .order_by(DeliveryTask.updated_at.desc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    items = []
    for task, title, amount_cents in rows:
        amount_usd = (amount_cents or 7500) / 100.0
        items.append(
            DeliveryTaskResponse(
                id=task.id,
                brief_id=task.brief_id,
                title=title or "Software Acceptance Task",
                state=task.state,
                amount_usd=amount_usd,
                contractor_name="Maya Lin",
                review_required=task.review_required,
                hold_reasons=task.hold_reasons or [],
                current_delivery_id=task.current_delivery_id,
                updated_at=task.updated_at
            )
        )
    return items

@router.get("/{task_id}", response_model=DeliveryTaskResponse)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DeliveryTask, BriefRevision.title, MandateVersion.amount_cents)
        .join(Brief, Brief.id == DeliveryTask.brief_id)
        .outerjoin(BriefRevision, BriefRevision.id == Brief.current_revision_id)
        .outerjoin(Mandate, Mandate.task_id == DeliveryTask.id)
        .outerjoin(MandateVersion, MandateVersion.id == Mandate.current_version_id)
        .where(DeliveryTask.id == task_id)
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    task, title, amount_cents = row
    return DeliveryTaskResponse(
        id=task.id,
        brief_id=task.brief_id,
        title=title or "Software Acceptance Task",
        state=task.state,
        amount_usd=(amount_cents or 7500) / 100.0,
        contractor_name="Maya Lin",
        review_required=task.review_required,
        hold_reasons=task.hold_reasons or [],
        current_delivery_id=task.current_delivery_id,
        updated_at=task.updated_at
    )
