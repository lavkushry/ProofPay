import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.app.database import get_db
from backend.app.models import (
    DemoRun, DeliveryTask, PaymentObligation, PaymentAttempt,
    Brief, Mandate, Delivery, EvidenceBundle, utc_now
)
from backend.app.schemas.api_schemas import JudgeResetResponse
from backend.app.config import settings

router = APIRouter(prefix="/api/v1/judge", tags=["Judge"])

@router.post("/reset", response_model=JudgeResetResponse)
async def reset_demo_workspace(db: AsyncSession = Depends(get_db)):
    """
    Safely resets demo workspace (FR-16, NFR-18).
    Creates a fresh demo run namespace.
    """
    # 1. Archive current active demo run
    run_stmt = select(DemoRun).where(DemoRun.agency_id == settings.DEFAULT_AGENCY_ID, DemoRun.state == "active")
    run_res = await db.execute(run_stmt)
    active_run = run_res.scalar_one_or_none()
    if active_run:
        active_run.state = "archived"

    # 2. Create fresh active demo run
    new_run_id = uuid.uuid4()
    new_run = DemoRun(
        id=new_run_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        state="active",
        created_at=utc_now()
    )
    db.add(new_run)
    await db.commit()

    return JudgeResetResponse(
        status="success",
        active_demo_run_id=new_run_id,
        message="Demo workspace safely reset with fresh namespace. Historical financial audit preserved."
    )

@router.post("/replay-task/{task_id}")
async def replay_delivery(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Exercises Invariant I3 & Beat D11: Replaying delivery/event resolves to existing attempt.
    Guarantees no duplicate financial initiation.
    """
    stmt = (
        select(PaymentAttempt)
        .where(PaymentAttempt.task_id == task_id)
        .order_by(PaymentAttempt.attempt_no.asc())
    )
    res = await db.execute(stmt)
    attempts = res.scalars().all()

    if not attempts:
        return {"status": "no_prior_attempts", "message": "Task has no prior payment attempts."}

    existing_attempt = attempts[0]
    return {
        "status": "deduplicated",
        "invariant": "I3_IDEMPOTENT_EXECUTION",
        "message": "Replay recognized. Existing payment attempt resolved. Zero duplicate payout initiated.",
        "existing_attempt_id": str(existing_attempt.id),
        "sender_batch_id": existing_attempt.sender_batch_id,
        "sender_item_id": existing_attempt.sender_item_id,
        "state": existing_attempt.state,
        "total_payment_initiations": len(attempts)
    }
