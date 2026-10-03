"""Atomic authorized domain callbacks, audit, outbox and scoped command receipts.

Callbacks perform database work only. External I/O belongs to leased stages
after commit. All callback writes roll back if the final receipt loses a race.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.errors import APIError
from backend.app.models import AuditLog, CommandReceipt, OutboxEvent
from backend.app.services.auth import reauthorize
from backend.app.services.locking import lock_workspace

# Public route aliases converge before hashing and receipt lookup.
COMMAND_FAMILIES = {
    "create_brief": "create_brief",
    "submit_delivery": "submit_delivery",
    "contractor_submit_delivery": "submit_delivery",
}


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def command_digest(actor, operation, body):
    family = COMMAND_FAMILIES[operation]
    validated = body.model_dump(mode="json") if isinstance(body, BaseModel) else body
    return canonical_digest({"agency_id": str(actor.agency_id), "principal_id": str(actor.principal_id),
                             "effective_user_id": str(actor.effective_user_id), "family": family,
                             "request": validated})


def idempotency_key(request):
    try:
        return uuid.UUID(request.headers.get("Idempotency-Key", ""))
    except ValueError:
        raise APIError(400, "INVALID_REQUEST", "A UUID Idempotency-Key is required.") from None


@dataclass(frozen=True)
class CommandResult:
    status: int
    body: dict
    task_id: uuid.UUID | None
    event_type: str
    event_payload: dict


def receipt_query(actor, family, key):
    return select(CommandReceipt).where(CommandReceipt.agency_id==actor.agency_id,
        CommandReceipt.principal_user_id==actor.principal_id, CommandReceipt.effective_user_id==actor.effective_user_id,
        CommandReceipt.operation==family, CommandReceipt.idempotency_key==key)


def replay(receipt, digest):
    if receipt.request_digest != digest:
        raise APIError(409, "IDEMPOTENCY_CONFLICT", "This key was already used with different command data.")
    return receipt.http_status, receipt.response


async def execute_command(db, actor, operation, key, body, correlation_id, authorize, mutate, *, task_id=None):
    family = COMMAND_FAMILIES[operation]
    digest = command_digest(actor, operation, body)
    # Authentication reads may have autobegun a transaction; no mutations precede this boundary.
    await db.rollback()
    try:
        async with db.begin():
            await reauthorize(db, actor)
            await authorize(db, actor)
            receipt = await db.scalar(receipt_query(actor, family, key))
            if receipt is not None:
                return replay(receipt, digest)
            await lock_workspace(db, actor.agency_id, task_id=task_id)
            await reauthorize(db, actor)
            await authorize(db, actor)
            receipt = await db.scalar(receipt_query(actor, family, key))
            if receipt is not None:
                return replay(receipt, digest)
            command_id = uuid.uuid4()
            result = await mutate(db, actor)
            job = OutboxEvent(id=uuid.uuid4(), agency_id=actor.agency_id, task_id=result.task_id,
                              event_type=result.event_type, dedup_key=f"command:{command_id}",
                              payload={**result.event_payload, "actor": {
                                  "principal_id": str(actor.principal_id), "effective_user_id": str(actor.effective_user_id)}})
            db.add(job)
            db.add(AuditLog(agency_id=actor.agency_id, principal_user_id=actor.principal_id,
                           effective_user_id=actor.effective_user_id, event_type=f"command.{family}",
                           correlation_id=correlation_id, references_json={"command_id": str(command_id), "job_id": str(job.id)},
                           details={"request_digest": digest}))
            # Receipt is the final concurrent gate; its failure rolls back every preceding write.
            await db.flush()
            db.add(CommandReceipt(id=command_id, agency_id=actor.agency_id, principal_user_id=actor.principal_id,
                                  effective_user_id=actor.effective_user_id, operation=family, idempotency_key=key,
                                  request_digest=digest, http_status=result.status, response=result.body))
            await db.flush()
            return result.status, result.body
    except IntegrityError as error:
        constraint = getattr(error.orig, "constraint_name", None)
        if constraint is None:
            constraint = getattr(getattr(error.orig, "__cause__", None), "constraint_name", "")
        if not str(constraint).startswith("command_receipts"):
            raise
        async with db.begin():
            await reauthorize(db, actor)
            await authorize(db, actor)
            receipt = await db.scalar(receipt_query(actor, family, key))
            if receipt is None:
                raise
            return replay(receipt, digest)
