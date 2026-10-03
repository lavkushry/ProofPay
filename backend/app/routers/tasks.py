import uuid
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_

from backend.app.database import get_db
from backend.app.models import Brief, BriefRevision, Contractor, DeliveryTask, Mandate, MandateVersion
from backend.app.schemas.api_schemas import DeliveryTaskResponse
from backend.app.services.auth import Actor, authorize_task, get_actor, visible_tasks

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


def task_projection(actor):
    return (
        visible_tasks(actor).add_columns(BriefRevision.title, MandateVersion.amount_cents, Contractor.display_name)
        .join(Brief, and_(Brief.agency_id==DeliveryTask.agency_id, Brief.id==DeliveryTask.brief_id))
        .outerjoin(BriefRevision, and_(BriefRevision.agency_id==Brief.agency_id, BriefRevision.id==Brief.current_revision_id))
        .outerjoin(Mandate, and_(Mandate.agency_id==DeliveryTask.agency_id, Mandate.task_id==DeliveryTask.id))
        .outerjoin(MandateVersion, and_(MandateVersion.agency_id==Mandate.agency_id, MandateVersion.id==Mandate.current_version_id))
        .outerjoin(Contractor, and_(Contractor.agency_id==MandateVersion.agency_id, Contractor.id==MandateVersion.contractor_id))
    )


def public_task(row):
    task, title, amount, contractor_name = row
    return DeliveryTaskResponse(id=task.id, brief_id=task.brief_id, title=title or "Untitled draft",
        state=task.state, amount_usd=(amount or 0)/100, contractor_name=contractor_name or "Unassigned",
        review_required=task.review_required, hold_reasons=task.hold_reasons,
        current_delivery_id=task.current_delivery_id, updated_at=task.updated_at)


@router.get("", response_model=List[DeliveryTaskResponse])
async def list_tasks(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(task_projection(actor).order_by(DeliveryTask.updated_at.desc()))).all()
    return [public_task(row) for row in rows]


@router.get("/{task_id}", response_model=DeliveryTaskResponse)
async def get_task(task_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    await authorize_task(db, actor, task_id)
    return public_task((await db.execute(task_projection(actor).where(DeliveryTask.id==task_id))).one())
