"""Draft/approval under the shared authority lock; no payment or model I/O."""

import copy
import uuid

from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.errors import APIError
from backend.app.models import (
    AcceptanceCheck, Agency, AIInteraction, Brief, BriefRevision, Compilation,
    Contractor, DeliveryTask, DemoRun, FixtureManifest, Mandate, MandateVersion,
    OutboxEvent, PaymentAttempt, PaymentObligation, RecipientBinding,
)
from backend.app.schemas.api_schemas import CheckProposal
from backend.app.schemas.commands import PaymentTerms
from backend.app.schemas.mandates import MandatePayload, MandateVersionResponse
from backend.app.services.auth import aware, now
from backend.app.services.catalog import validated_snapshot
from backend.app.services.commands import CommandResult, canonical_digest
from backend.app.services.compiler import compilation_input, validate_proposal


async def mandate_for_task(db, actor, task_id):
    row = (await db.execute(select(Mandate, DeliveryTask).join(DeliveryTask,
        (DeliveryTask.agency_id==Mandate.agency_id)&(DeliveryTask.id==Mandate.task_id))
        .where(Mandate.agency_id==actor.agency_id, Mandate.task_id==task_id)
        .execution_options(populate_existing=True))).first()
    if row is None:
        raise APIError(404, "NOT_FOUND", "Mandate not found.")
    return row


async def owned_mandate(db, actor, mandate_id):
    if actor.role != "owner":
        raise APIError(403, "FORBIDDEN", "Only the owner may change mandate authority.")
    task_id = await db.scalar(select(Mandate.task_id).where(
        Mandate.agency_id==actor.agency_id, Mandate.id==mandate_id))
    if task_id is None:
        raise APIError(404, "NOT_FOUND", "Mandate not found.")
    return await mandate_for_task(db, actor, task_id)


def public_version(version):
    return MandateVersionResponse.model_validate({"id": version.id, "mandate_id": version.mandate_id, "version": version.version,
            "lifecycle_state": version.lifecycle_state, "digest": version.payload_digest,
            "snapshot": version.public_payload, "created_at": version.created_at}).model_dump(mode="json")


def visible_versions(actor, mandate_id):
    query = select(MandateVersion).where(MandateVersion.agency_id==actor.agency_id,
                                         MandateVersion.mandate_id==mandate_id)
    if actor.role == "contractor":
        query = query.join(Contractor, (Contractor.agency_id==MandateVersion.agency_id)&
            (Contractor.id==MandateVersion.contractor_id)).where(
                Contractor.user_id==actor.effective_user_id, MandateVersion.approved_at.is_not(None))
    elif actor.role != "owner":
        raise APIError(403, "FORBIDDEN", "Choose an owner or contractor persona.")
    return query


async def read_mandate(db, actor, mandate_id):
    mandate = await db.scalar(select(Mandate).where(Mandate.agency_id==actor.agency_id, Mandate.id==mandate_id))
    versions = (await db.scalars(visible_versions(actor, mandate_id)
        .order_by(MandateVersion.version.desc()).limit(50))).all()
    if mandate is None or (actor.role != "owner" and not versions):
        raise APIError(404, "NOT_FOUND", "Mandate not found.")
    current = mandate.current_version_id
    if actor.role != "owner" and not any(v.id==current for v in versions):
        current = None
    return {"id": str(mandate.id), "task_id": str(mandate.task_id),
            "current_version_id": str(current) if current else None,
            "versions": [public_version(v) for v in versions]}


async def read_version(db, actor, mandate_id, version_id):
    version = await db.scalar(visible_versions(actor, mandate_id).where(MandateVersion.id==version_id))
    if version is None:
        raise APIError(404, "NOT_FOUND", "Mandate version not found.")
    return public_version(version)


async def approved_compilation(db, actor, task, revision_id, compilation_id):
    """Revalidate immutable sources instead of trusting the mutable ready projection."""
    brief = await db.scalar(select(Brief).where(Brief.agency_id==actor.agency_id, Brief.id==task.brief_id))
    revision = await db.scalar(select(BriefRevision).where(BriefRevision.agency_id==actor.agency_id,
        BriefRevision.id==revision_id, BriefRevision.brief_id==task.brief_id))
    compilation = await db.scalar(select(Compilation).where(Compilation.agency_id==actor.agency_id,
        Compilation.id==compilation_id, Compilation.brief_revision_id==revision_id))
    if brief is None or revision is None or brief.current_revision_id != revision_id:
        raise APIError(409, "STALE_REVISION", "Approval requires the current brief revision.")
    if compilation is None or compilation.status != "ready" or compilation.interaction_id is None:
        raise APIError(409, "COMPILATION_NOT_READY", "Approval requires a validated, unambiguous compilation.")
    manifest = await db.scalar(select(FixtureManifest).where(FixtureManifest.agency_id==actor.agency_id,
                                                             FixtureManifest.id==revision.manifest_id))
    if manifest is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Trusted manifest is unavailable.")
    contract = validated_snapshot(manifest)
    interaction = await db.scalar(select(AIInteraction).where(AIInteraction.agency_id==actor.agency_id,
        AIInteraction.id==compilation.interaction_id, AIInteraction.job_id==compilation.job_id,
        AIInteraction.brief_revision_id==revision.id, AIInteraction.stage=="compiler",
        AIInteraction.validated.is_(True), AIInteraction.error_code.is_(None)))
    job = await db.scalar(select(OutboxEvent).where(OutboxEvent.agency_id==actor.agency_id,
        OutboxEvent.id==compilation.job_id, OutboxEvent.task_id==task.id,
        OutboxEvent.event_type=="compile_requested", OutboxEvent.state=="done"))
    _prompt, input_digest = compilation_input(contract, revision)
    refs = {"brief_revision_id": str(revision.id), "manifest_id": str(manifest.id)}
    if (interaction is None or job is None or interaction.input_refs != refs or
        interaction.input_digest != input_digest or interaction.output != compilation.proposal or
        interaction.output_digest != canonical_digest(compilation.proposal) or
        job.payload.get("brief_id") != str(brief.id) or job.payload.get("revision_id") != str(revision.id) or
        job.payload.get("revision_digest") != revision.digest or job.payload.get("manifest_id") != str(manifest.id)):
        raise APIError(409, "STALE_COMPILATION", "Compiler output does not match its recorded inputs.")
    try:
        proposal = CheckProposal.model_validate(compilation.proposal, strict=True)
        if proposal.model_dump(mode="json") != compilation.proposal:
            raise ValueError("Incomplete compiler proposal")
        status, _ = validate_proposal(proposal, contract, revision.family)
    except (ValidationError, ValueError, TypeError):
        status = "ambiguous"
    if status != "ready":
        raise APIError(409, "COMPILATION_NOT_READY", "Compiled checks do not match the reviewed templates.")
    return proposal.model_dump(mode="json")["checks"]


async def active_obligation(db, actor, task):
    agency = await db.get(Agency, actor.agency_id)
    run = await db.scalar(select(DemoRun).where(DemoRun.agency_id==actor.agency_id,
        DemoRun.id==task.demo_run_id, DemoRun.state=="active"))
    if run is None or agency.current_demo_run_id != task.demo_run_id or task.state == "cancelled":
        raise APIError(409, "STALE_TASK", "Mandate authority requires an active workspace task.")
    # The shared agency lock serializes executor changes. The API reads financial
    # history without UPDATE grants (PostgreSQL requires those for FOR UPDATE).
    obligation = await db.scalar(select(PaymentObligation).where(PaymentObligation.agency_id==actor.agency_id,
        PaymentObligation.task_id==task.id))
    if obligation is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Payment obligation is unavailable.")
    successful = await db.scalar(select(PaymentAttempt.id).where(PaymentAttempt.agency_id==actor.agency_id,
        PaymentAttempt.obligation_id==obligation.id, PaymentAttempt.successful.is_(True)))
    if obligation.success_attempt_id is not None or successful is not None or task.state == "paid":
        raise APIError(409, "OBLIGATION_SETTLED", "This milestone has already been paid.")
    return obligation


async def recipient(db, actor, recipient_ref, *, binding_id=None):
    contractor = await db.scalar(select(Contractor).where(Contractor.agency_id==actor.agency_id,
                                                          Contractor.recipient_ref==recipient_ref))
    if contractor is None or contractor.current_binding_id is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "A confirmed recipient binding must be configured.")
    if binding_id is not None and contractor.current_binding_id != binding_id:
        raise APIError(409, "STALE_RECIPIENT", "Recipient binding changed; create and inspect a new draft.")
    binding = await db.scalar(select(RecipientBinding).where(RecipientBinding.agency_id==actor.agency_id,
        RecipientBinding.contractor_id==contractor.id, RecipientBinding.id==contractor.current_binding_id,
        RecipientBinding.confirmed_at.is_not(None)))
    if binding is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "A confirmed recipient binding must be configured.")
    return contractor, binding


def draft_payload(mandate, number, terms, contractor, binding, checks):
    return MandatePayload.model_validate({
        "mandate_id": str(mandate.id), "version": number, "status": "draft",
        "payer": {"account_ref": "payer_sandbox_us"},
        "payee": {"recipient_ref": contractor.recipient_ref, "display_name": contractor.display_name,
                  "email_hash": binding.receiver_hash},
        "amount": terms.amount.model_dump(mode="json"),
        "budget": {"max_total": terms.principal_cap.value, "max_attempts": terms.max_attempts},
        "authority": {"type": "conditional_release", "condition": "all checks pass", "expires_at": terms.expires_at},
        "acceptance_checks": checks, "audit": {"approved_by": None, "approved_at": None, "immutable": False},
    }).model_dump(mode="json")


def expect_current(mandate, expected):
    if mandate.current_version_id != expected:
        raise APIError(409, "STALE_MANDATE", "Current mandate authority changed; reload before continuing.")


async def create_draft(db, actor, mandate, task, body, *, first=False):
    await active_obligation(db, actor, task)
    number = (await db.scalar(select(func.max(MandateVersion.version)).where(
        MandateVersion.agency_id==actor.agency_id, MandateVersion.mandate_id==mandate.id)) or 0) + 1
    if first and number != 1:
        raise APIError(409, "MANDATE_EXISTS", "Use the versions endpoint to create a replacement draft.")
    if not first:
        expect_current(mandate, body.expected_current_version_id)
    if body.terms.expires_at <= now():
        raise APIError(409, "MANDATE_EXPIRED", "Draft expiry must be in the future.")
    checks = await approved_compilation(db, actor, task, body.brief_revision_id, body.compilation_id)
    contractor, binding = await recipient(db, actor, body.terms.recipient_ref)
    payload = draft_payload(mandate, number, body.terms, contractor, binding, checks)
    version = MandateVersion(id=uuid.uuid4(), agency_id=actor.agency_id, task_id=task.id,
        mandate_id=mandate.id, version=number, brief_revision_id=body.brief_revision_id,
        compilation_id=body.compilation_id, contractor_id=contractor.id, recipient_binding_id=binding.id,
        lifecycle_state="draft", amount_cents=body.terms.amount.cents,
        principal_cap_cents=body.terms.principal_cap.cents, currency="USD", max_attempts=body.terms.max_attempts,
        expires_at=body.terms.expires_at, public_payload=payload, payload_digest=canonical_digest(payload), created_at=now())
    db.add(version)
    await db.flush()
    for check in checks:
        db.add(AcceptanceCheck(agency_id=actor.agency_id, mandate_version_id=version.id, **check))
    return CommandResult(201, public_version(version), task.id, "mandate_recorded",
        {"mandate_id": str(mandate.id), "version_id": str(version.id)})


async def approve(db, actor, mandate, task, version_id, body):
    obligation = await active_obligation(db, actor, task)
    expect_current(mandate, body.expected_current_version_id)
    version = await db.scalar(select(MandateVersion).where(MandateVersion.agency_id==actor.agency_id,
        MandateVersion.mandate_id==mandate.id, MandateVersion.id==version_id).with_for_update())
    if version is None:
        raise APIError(404, "NOT_FOUND", "Mandate version not found.")
    if version.lifecycle_state != "draft":
        raise APIError(409, "STALE_MANDATE", "Only a draft may be approved.")
    if version.payload_digest != body.expected_draft_digest or canonical_digest(version.public_payload) != version.payload_digest:
        raise APIError(409, "STALE_MANDATE", "Draft digest changed; inspect the draft before approval.")
    if aware(version.expires_at) <= now():
        raise APIError(409, "MANDATE_EXPIRED", "Expired authority cannot be approved.")
    checks = await approved_compilation(db, actor, task, version.brief_revision_id, version.compilation_id)
    try:
        snapshot = MandatePayload.model_validate(version.public_payload)
        terms = PaymentTerms.model_validate({"recipient_ref": snapshot.payee.recipient_ref,
            "amount": snapshot.amount.model_dump(), "principal_cap": {"currency": "USD", "value": snapshot.budget.max_total},
            "max_attempts": snapshot.budget.max_attempts, "expires_at": snapshot.authority.expires_at})
    except ValidationError:
        raise APIError(409, "STALE_MANDATE", "Draft terms are invalid.") from None
    contractor, binding = await recipient(db, actor, terms.recipient_ref, binding_id=version.recipient_binding_id)
    expected_payload = draft_payload(mandate, version.version, terms, contractor, binding, checks)
    # Names in the inspected draft remain stable even when the directory label changes.
    expected_payload["payee"]["display_name"] = snapshot.payee.display_name
    if (version.public_payload != expected_payload or version.contractor_id != contractor.id or
        version.amount_cents != terms.amount.cents or version.principal_cap_cents != terms.principal_cap.cents or
        version.max_attempts != terms.max_attempts or version.currency != "USD" or
        aware(version.expires_at) != terms.expires_at):
        raise APIError(409, "STALE_MANDATE", "Draft snapshot does not match its bound records.")
    records = (await db.scalars(select(AcceptanceCheck).where(AcceptanceCheck.agency_id==actor.agency_id,
        AcceptanceCheck.mandate_version_id==version.id).order_by(AcceptanceCheck.check_id))).all()
    actual = [{"check_id": c.check_id, "template_type": c.template_type, "params": c.params,
               "compiled_by": c.compiled_by, "approved": c.approved} for c in records]
    if actual != checks:
        raise APIError(409, "STALE_MANDATE", "Draft check records changed.")
    if version.principal_cap_cents < obligation.reserved_cents + obligation.consumed_cents:
        raise APIError(409, "BUDGET_EXCEEDED", "Replacement cap cannot discard existing reserved or consumed principal.")
    if version.max_attempts < obligation.next_attempt_no - 1:
        raise APIError(409, "ATTEMPT_LIMIT", "Replacement authority cannot discard prior business attempts.")
    unresolved = await db.scalar(select(PaymentAttempt.id).where(PaymentAttempt.agency_id==actor.agency_id,
        PaymentAttempt.obligation_id==obligation.id, PaymentAttempt.unresolved.is_(True)))
    for check in records:
        check.approved = True
    await db.flush()  # Checks remain editable only while their parent is a draft.
    if mandate.current_version_id is not None:
        previous = await db.scalar(select(MandateVersion).where(MandateVersion.agency_id==actor.agency_id,
            MandateVersion.mandate_id==mandate.id, MandateVersion.id==mandate.current_version_id).with_for_update())
        if previous is None:
            raise APIError(409, "STALE_MANDATE", "Current authority is unavailable.")
        if previous.lifecycle_state == "approved":
            previous.lifecycle_state = "superseded"
            await db.flush()  # Release the unique approved-version slot before approval.
    stamp = now()
    payload = copy.deepcopy(version.public_payload)
    payload["status"] = "approved"
    payload["audit"] = {"approved_by": str(actor.effective_user_id), "approved_at": stamp.isoformat(), "immutable": True}
    for check in payload["acceptance_checks"]:
        check["approved"] = True
    payload = MandatePayload.model_validate(payload).model_dump(mode="json")
    version.public_payload, version.payload_digest = payload, canonical_digest(payload)
    version.lifecycle_state, version.approved_by, version.approved_at = "approved", actor.effective_user_id, stamp
    mandate.current_version_id = version.id
    task.current_delivery_id, task.current_bundle_id = None, None
    task.review_required = False
    financial = task.state in {"payment_initiated", "reconciling", "failed", "unclaimed"}
    if unresolved is None and not financial:
        task.state = "awaiting_delivery"
    if unresolved is not None:
        task.hold_reasons = list(dict.fromkeys([*task.hold_reasons, "PAYMENT_IN_PROGRESS"]))
    else:
        task.hold_reasons = ["NEW_MANDATE_REQUIRES_DELIVERY"] if financial else []
    task.version += 1
    task.updated_at = stamp
    return CommandResult(200, public_version(version), task.id, "mandate_recorded",
        {"mandate_id": str(mandate.id), "version_id": str(version.id)})
