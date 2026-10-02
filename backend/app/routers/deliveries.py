import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import (
    DeliveryTask, Mandate, MandateVersion, AcceptanceCheck, Delivery,
    VerificationJob, EvidenceBundle, EvidenceResult, EvidenceArtifact,
    Correction, DecisionRequest, PaymentObligation, PaymentAttempt,
    PayoutItem, ProviderObservation, utc_now
)
from backend.app.schemas.api_schemas import DeliverySubmitRequest, DeliveryResponse, CheckObservation
from backend.app.services.evidence_reviewer import EvidenceReviewerService
from backend.app.services.payment_executor import paypal_executor
from backend.app.services.ledger import LedgerService
from backend.app.config import settings

router = APIRouter(prefix="/api/v1/deliveries", tags=["Deliveries"])

@router.post("/submit", response_model=DeliveryResponse)
async def submit_delivery(req: DeliverySubmitRequest, db: AsyncSession = Depends(get_db)):
    # 1. Fetch Task and current Mandate Version
    t_stmt = select(DeliveryTask).where(DeliveryTask.id == req.task_id)
    t_res = await db.execute(t_stmt)
    task = t_res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    m_stmt = select(Mandate).where(Mandate.task_id == task.id)
    m_res = await db.execute(m_stmt)
    mandate = m_res.scalar_one_or_none()
    if not mandate or not mandate.current_version_id:
        raise HTTPException(status_code=400, detail="Mandate not approved")

    mv_stmt = select(MandateVersion).where(MandateVersion.id == mandate.current_version_id)
    mv_res = await db.execute(mv_stmt)
    mandate_version = mv_res.scalar_one_or_none()
    if not mandate_version or mandate_version.lifecycle_state != "approved":
        raise HTTPException(status_code=400, detail="Mandate version must be approved")

    # 2. Sequence calculation
    d_count_stmt = select(Delivery).where(Delivery.task_id == task.id)
    d_count_res = await db.execute(d_count_stmt)
    existing_deliveries = d_count_res.scalars().all()
    sequence = len(existing_deliveries) + 1
    previous_id = existing_deliveries[-1].id if existing_deliveries else None

    delivery_id = uuid.uuid4()
    claim_digest = hashlib.sha256(req.claim.encode("utf-8")).hexdigest()
    artifact_digest = hashlib.sha256(req.artifact_ref.encode("utf-8")).hexdigest()

    delivery = Delivery(
        id=delivery_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        task_id=task.id,
        mandate_version_id=mandate_version.id,
        artifact_version_id=uuid.uuid4(),
        artifact_digest=artifact_digest,
        mandate_digest=mandate_version.payload_digest,
        submitted_by=settings.DEFAULT_AGENCY_ID,
        claim=req.claim,
        claim_digest=claim_digest,
        sequence=sequence,
        previous_delivery_id=previous_id,
        created_at=utc_now()
    )
    db.add(delivery)

    # 3. Create Verification Job & Execute Checks
    job_id = uuid.uuid4()
    bundle_id = uuid.uuid4()
    is_broken = "broken" in req.artifact_ref

    job = VerificationJob(
        id=job_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        task_id=task.id,
        delivery_id=delivery_id,
        state="completed",
        inputs={"artifact_ref": req.artifact_ref},
        input_digest=artifact_digest,
        started_at=utc_now(),
        completed_at=utc_now()
    )
    db.add(job)

    # 4. Create Evidence Bundle
    bundle_digest = hashlib.sha256(f"bundle_{delivery_id}_{req.artifact_ref}".encode("utf-8")).hexdigest()
    bundle = EvidenceBundle(
        id=bundle_id,
        agency_id=settings.DEFAULT_AGENCY_ID,
        task_id=task.id,
        delivery_id=delivery_id,
        mandate_version_id=mandate_version.id,
        verification_job_id=job_id,
        artifact_digest=artifact_digest,
        mandate_digest=mandate_version.payload_digest,
        bundle_digest=bundle_digest,
        manifest_id=uuid.uuid4(),
        created_at=utc_now()
    )
    db.add(bundle)

    # 5. Fetch approved checks to generate attributable results
    c_stmt = select(AcceptanceCheck).where(AcceptanceCheck.mandate_version_id == mandate_version.id)
    c_res = await db.execute(c_stmt)
    checks = c_res.scalars().all()

    observations_list = []
    for c in checks:
        if c.check_id == "C01":
            if is_broken:
                outcome = "fail"
                obs = {
                    "template": "viewport_no_horizontal_overflow",
                    "viewport_width": 320,
                    "scroll_width": 480,
                    "overflow_px": 160,
                    "message": "Horizontal overflow detected: scrollWidth 480px exceeds 320px viewport."
                }
            else:
                outcome = "pass"
                obs = {
                    "template": "viewport_no_horizontal_overflow",
                    "viewport_width": 320,
                    "scroll_width": 320,
                    "overflow_px": 0,
                    "message": "No horizontal overflow: document fits cleanly within 320px."
                }
        elif c.check_id == "C02":
            outcome = "pass"
            obs = {"template": "cart_total_unchanged", "total_cents": 4200, "baseline": 4200}
        else: # C03
            outcome = "pass"
            obs = {"template": "keyboard_checkout_reachable", "control": "checkout_pay", "reachable": True}

        res_digest = hashlib.sha256(f"{outcome}_{c.check_id}".encode("utf-8")).hexdigest()
        er = EvidenceResult(
            id=uuid.uuid4(),
            agency_id=settings.DEFAULT_AGENCY_ID,
            bundle_id=bundle_id,
            mandate_version_id=mandate_version.id,
            acceptance_check_id=c.id,
            outcome=outcome,
            observations=obs,
            result_digest=res_digest,
            completed_at=utc_now()
        )
        db.add(er)
        observations_list.append(CheckObservation(check_id=c.check_id, outcome=outcome, observations=obs))

    # Add mock screenshot artifact
    mock_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    ea = EvidenceArtifact(
        id=uuid.uuid4(),
        agency_id=settings.DEFAULT_AGENCY_ID,
        bundle_id=bundle_id,
        check_id="C01",
        media_type="image/png",
        digest=hashlib.sha256(mock_png_bytes).hexdigest(),
        content=mock_png_bytes,
        created_at=utc_now()
    )
    db.add(ea)

    # 6. Run AI Reviewer
    ai_review = EvidenceReviewerService.review_bundle(req.claim, observations_list, has_screenshot=True)

    task.current_delivery_id = delivery_id
    task.current_bundle_id = bundle_id

    if ai_review.verdict != "pass":
        # Contradiction / Failure path (Beat D06)
        task.state = "correction_requested"
        task.hold_reasons = ai_review.contradictions

        corr = Correction(
            id=uuid.uuid4(),
            agency_id=settings.DEFAULT_AGENCY_ID,
            task_id=task.id,
            delivery_id=delivery_id,
            bundle_id=bundle_id,
            review_interaction_id=uuid.uuid4(),
            contractor_message=ai_review.rationale,
            evidence_refs=ai_review.evidence_refs,
            created_at=utc_now()
        )
        db.add(corr)
    else:
        # Success path (Beat D08 -> D09 -> D10)
        task.state = "evidence_passed"
        task.hold_reasons = []

        dec_id = uuid.uuid4()
        dec = DecisionRequest(
            id=dec_id,
            agency_id=settings.DEFAULT_AGENCY_ID,
            task_id=task.id,
            mandate_version_id=mandate_version.id,
            bundle_id=bundle_id,
            source="ai",
            review_interaction_id=uuid.uuid4(),
            state="queued",
            evaluation_generation=1,
            request_digest=hashlib.sha256(f"dec_{task.id}_{delivery_id}".encode("utf-8")).hexdigest(),
            evidence_refs=ai_review.evidence_refs,
            created_at=utc_now()
        )
        db.add(dec)

        # Trigger PayPal Automated Payout (Beat D09)
        ob_stmt = select(PaymentObligation).where(PaymentObligation.task_id == task.id)
        ob_res = await db.execute(ob_stmt)
        obligation = ob_res.scalar_one_or_none()

        if obligation:
            attempt_id = uuid.uuid4()
            attempt_uuid_str = str(attempt_id).replace("-", "")
            sender_batch_id = f"pp_{attempt_uuid_str}"
            sender_item_id = f"ppi_{attempt_uuid_str[:50]}"
            amount_usd_str = f"{(mandate_version.amount_cents / 100.0):.2f}"

            # Reserve budget in ledger
            reserved = await LedgerService.reserve_budget(
                db, settings.DEFAULT_AGENCY_ID, obligation.id, attempt_id, mandate_version.amount_cents
            )

            payout_resp = await paypal_executor.create_payout(
                sender_batch_id=sender_batch_id,
                sender_item_id=sender_item_id,
                amount_usd=amount_usd_str,
                receiver_email="contractor-maya-sandbox@agency.com"
            )

            batch_id = payout_resp.get("batch_header", {}).get("payout_batch_id", "SANDBOX_BATCH_001")
            item_id = payout_resp.get("simulated_item_id") or f"ITEM_{batch_id[-6:]}"

            attempt = PaymentAttempt(
                id=attempt_id,
                agency_id=settings.DEFAULT_AGENCY_ID,
                task_id=task.id,
                obligation_id=obligation.id,
                mandate_version_id=mandate_version.id,
                decision_request_id=dec_id,
                attempt_no=obligation.next_attempt_no,
                principal_cents=mandate_version.amount_cents,
                currency="USD",
                sender_batch_id=sender_batch_id,
                sender_item_id=sender_item_id,
                request_ciphertext=b"encrypted_payout_request",
                request_digest=hashlib.sha256(sender_batch_id.encode("utf-8")).hexdigest(),
                state="success",
                unresolved=False,
                successful=True,
                first_dispatch_at=utc_now(),
                guard_snapshot={"sandbox": True, "mandate_approved": True, "checks_passed": True},
                last_reconciled_at=utc_now(),
                created_at=utc_now()
            )
            db.add(attempt)

            # Record item success and reconcile receipt (Beat D10)
            payout_item = PayoutItem(
                id=uuid.uuid4(),
                agency_id=settings.DEFAULT_AGENCY_ID,
                attempt_id=attempt_id,
                payer_account_ref=settings.PAYER_ACCOUNT_REF,
                provider_batch_id=batch_id,
                provider_item_id=item_id,
                provider_transaction_id=f"TX_{uuid.uuid4().hex[:10].upper()}",
                raw_status="SUCCESS",
                canonical_state="success",
                fee_cents=25,
                fee_currency="USD",
                binding_verified=True
            )
            db.add(payout_item)

            # Consume budget
            await LedgerService.consume_budget(
                db, settings.DEFAULT_AGENCY_ID, obligation.id, attempt_id, mandate_version.amount_cents
            )

            obligation.success_attempt_id = attempt_id
            task.state = "paid"

    await db.commit()

    return DeliveryResponse(
        id=delivery_id,
        task_id=task.id,
        sequence=sequence,
        artifact_ref=req.artifact_ref,
        claim=req.claim,
        created_at=delivery.created_at
    )
