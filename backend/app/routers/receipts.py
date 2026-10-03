import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import (
    DeliveryTask, Brief, BriefRevision, Mandate, MandateVersion,
    EvidenceBundle, PaymentObligation, PaymentAttempt, PayoutItem, Contractor
)
from backend.app.schemas.api_schemas import ReceiptResponse
from backend.app.services.auth import Actor, authorize_task, get_actor

router = APIRouter(prefix="/api/v1/receipts", tags=["Receipts"])

@router.get("/{task_id}", response_model=ReceiptResponse)
async def get_receipt(task_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    await authorize_task(db, actor, task_id)
    # 1. Fetch Task
    t_stmt = select(DeliveryTask).where(DeliveryTask.id == task_id)
    t_res = await db.execute(t_stmt)
    task = t_res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. Fetch Brief Title
    b_stmt = select(BriefRevision.title).join(Brief, Brief.current_revision_id == BriefRevision.id).where(Brief.id == task.brief_id)
    b_res = await db.execute(b_stmt)
    title = b_res.scalar_one_or_none() or "Acceptance Verified Task"

    # 3. Fetch Mandate info
    m_stmt = select(MandateVersion).join(Mandate, Mandate.current_version_id == MandateVersion.id).where(Mandate.task_id == task_id)
    m_res = await db.execute(m_stmt)
    mandate_version = m_res.scalar_one_or_none()

    mandate_digest = mandate_version.payload_digest if mandate_version else "N/A"
    amount_usd = (mandate_version.amount_cents / 100.0) if mandate_version else 0.0
    recipient_ref = await db.scalar(select(Contractor.recipient_ref).where(Contractor.agency_id==actor.agency_id, Contractor.id==mandate_version.contractor_id)) if mandate_version else None

    # 4. Fetch Evidence Bundle info
    bundle_digest = "N/A"
    if task.current_bundle_id:
        eb_stmt = select(EvidenceBundle.bundle_digest).where(EvidenceBundle.id == task.current_bundle_id)
        eb_res = await db.execute(eb_stmt)
        bundle_digest = eb_res.scalar_one_or_none() or "N/A"

    # 5. Fetch Payment Item details
    item_stmt = (
        select(PayoutItem, PaymentAttempt)
        .join(PaymentAttempt, PaymentAttempt.id == PayoutItem.attempt_id)
        .where(PaymentAttempt.task_id == task_id)
    )
    item_res = await db.execute(item_stmt)
    item_row = item_res.first()

    if item_row:
        payout_item, attempt = item_row
        return ReceiptResponse(
            task_id=task.id,
            brief_title=title,
            contractor_ref=recipient_ref or "unassigned",
            amount_usd=amount_usd,
            currency="USD",
            item_status=payout_item.canonical_state,
            provider_batch_id=payout_item.provider_batch_id,
            provider_item_id=payout_item.provider_item_id,
            mandate_digest=mandate_digest,
            bundle_digest=bundle_digest,
            paid_at=payout_item.updated_at if payout_item.canonical_state=="success" and payout_item.binding_verified else None
        )

    return ReceiptResponse(
        task_id=task.id,
        brief_title=title,
        contractor_ref=recipient_ref or "unassigned",
        amount_usd=amount_usd,
        currency="USD",
        item_status="pending_release",
        provider_batch_id=None,
        provider_item_id=None,
        mandate_digest=mandate_digest,
        bundle_digest=bundle_digest,
        paid_at=None
    )
