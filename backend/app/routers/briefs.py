import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import (
    Brief, BriefRevision, DeliveryTask, Mandate, MandateVersion,
    AcceptanceCheck, PaymentObligation, DemoRun, utc_now
)
from backend.app.schemas.api_schemas import BriefCreateRequest, BriefResponse, CheckProposal
from backend.app.services.brief_compiler import BriefCompilerService
from backend.app.config import settings

router = APIRouter(prefix="/api/v1/briefs", tags=["Briefs"])

@router.post("", response_model=BriefResponse)
async def create_and_compile_brief(req: BriefCreateRequest, db: AsyncSession = Depends(get_db)):
    # 1. Compile checks via AI service
    proposal = BriefCompilerService.compile_brief(req.family, req.body)
    if proposal.ambiguities:
        # Ambiguity detected
        pass

    # 2. Get active demo run
    demo_stmt = select(DemoRun).where(DemoRun.agency_id == settings.DEFAULT_AGENCY_ID, DemoRun.state == "active")
    demo_res = await db.execute(demo_stmt)
    demo_run = demo_res.scalar_one_or_none()
    demo_run_id = demo_run.id if demo_run else uuid.uuid4()

    # 3. Create Brief
    brief_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    user_id = settings.DEFAULT_AGENCY_ID

    brief = Brief(
        id=brief_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        current_revision_id=revision_id,
        created_by=user_id,
        created_at=utc_now()
    )

    amount_cents = int(req.amount_usd * 100)
    proposed_terms = {
        "amount_cents": amount_cents,
        "currency": "USD",
        "contractor_ref": req.contractor_ref,
        "family": req.family
    }
    digest = BriefCompilerService.calculate_digest({"title": req.title, "body": req.body, "terms": proposed_terms})

    revision = BriefRevision(
        id=revision_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        brief_id=brief_id,
        revision=1,
        title=req.title,
        body=req.body,
        family=req.family,
        manifest_id=uuid.uuid4(),
        proposed_terms=proposed_terms,
        digest=digest,
        created_at=utc_now()
    )

    # 4. Create Delivery Task
    task_id = uuid.uuid4()
    task = DeliveryTask(
        id=task_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        demo_run_id=demo_run_id,
        brief_id=brief_id,
        state="brief_captured",
        created_at=utc_now() if hasattr(DeliveryTask, "created_at") else None
    )

    # 5. Create Draft Mandate and Mandate Version
    mandate_id = uuid.uuid4()
    mandate_version_id = uuid.uuid4()

    mandate = Mandate(
        id=mandate_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        task_id=task_id,
        current_version_id=mandate_version_id
    )

    payload = {
        "mandate_id": str(mandate_id),
        "version": 1,
        "amount_cents": amount_cents,
        "currency": "USD",
        "checks": [c.model_dump() for c in proposal.checks]
    }
    payload_digest = BriefCompilerService.calculate_digest(payload)

    mandate_version = MandateVersion(
        id=mandate_version_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        task_id=task_id,
        mandate_id=mandate_id,
        version=1,
        brief_revision_id=revision_id,
        compilation_id=uuid.uuid4(),
        contractor_id=uuid.uuid4(),
        recipient_binding_id=uuid.uuid4(),
        lifecycle_state="draft",
        amount_cents=amount_cents,
        principal_cap_cents=amount_cents,
        currency="USD",
        max_attempts=3,
        expires_at=utc_now() + timedelta(hours=req.expires_in_hours),
        public_payload=payload,
        payload_digest=payload_digest,
        created_at=utc_now()
    )

    # 6. Add Acceptance Checks to mandate version
    for c in proposal.checks:
        ac = AcceptanceCheck(
            id=uuid.uuid4(),
            agency_id=settings.DEFAULT_AGENCY_ID,
            mandate_version_id=mandate_version_id,
            check_id=c.check_id,
            template_type=c.template_type,
            params=c.params,
            compiled_by="ai",
            approved=False
        )
        db.add(ac)

    # 7. Create Payment Obligation for the task
    obligation = PaymentObligation(
        id=uuid.uuid4(),
        agency_id=settings.DEFAULT_AGENCY_ID,
        task_id=task_id,
        currency="USD",
        next_attempt_no=1,
        reserved_cents=0,
        consumed_cents=0
    )

    db.add(brief)
    db.add(revision)
    db.add(task)
    db.add(mandate)
    db.add(mandate_version)
    db.add(obligation)
    await db.commit()

    return BriefResponse(
        id=brief_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        current_revision_id=revision_id,
        title=req.title,
        body=req.body,
        family=req.family,
        proposal=proposal
    )
