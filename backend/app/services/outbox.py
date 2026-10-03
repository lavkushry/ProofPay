"""Short PostgreSQL claims, durable stage outputs and fenced atomic completion."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, or_, select, update

from backend.app.models import AuditLog, OutboxEvent
from backend.app.services.locking import lock_workspace


class LeaseLost(Exception):
    pass


class StageConflict(Exception):
    pass


@dataclass(frozen=True)
class Lease:
    id: uuid.UUID
    agency_id: uuid.UUID
    task_id: uuid.UUID | None
    token: uuid.UUID
    event_type: str
    payload: dict
    stage_state: dict
    attempt: int


def ownership(lease):
    return (OutboxEvent.id==lease.id, OutboxEvent.agency_id==lease.agency_id,
            OutboxEvent.state=="leased", OutboxEvent.lease_token==lease.token,
            OutboxEvent.lease_until > func.clock_timestamp())


async def claim(factory, *, lease_seconds=120, max_attempts=3):
    async with factory.begin() as db:
        eligible = or_(and_(OutboxEvent.state=="ready", OutboxEvent.available_at<=func.clock_timestamp()),
                       and_(OutboxEvent.state=="leased", OutboxEvent.lease_until<=func.clock_timestamp()))
        job = await db.scalar(select(OutboxEvent).where(eligible).order_by(OutboxEvent.available_at, OutboxEvent.id).limit(1).with_for_update(skip_locked=True))
        if job is None:
            return None
        if job.attempt_count >= max_attempts:
            job.state, job.lease_token, job.lease_until = "failed", None, None
            job.last_error_code = "RETRY_EXHAUSTED"
            job.updated_at = func.clock_timestamp()
            return None
        token = uuid.uuid4()
        job.state, job.lease_token = "leased", token
        job.lease_until = func.clock_timestamp()+timedelta(seconds=lease_seconds)
        job.attempt_count += 1
        job.updated_at = func.clock_timestamp()
        return Lease(job.id, job.agency_id, job.task_id, token, job.event_type,
                     job.payload, dict(job.stage_state), job.attempt_count)


async def heartbeat(factory, lease, *, lease_seconds=120):
    async with factory.begin() as db:
        changed = await db.scalar(update(OutboxEvent).where(*ownership(lease)).values(
            lease_until=func.clock_timestamp()+timedelta(seconds=lease_seconds), updated_at=func.clock_timestamp()).returning(OutboxEvent.id))
        if changed is None:
            raise LeaseLost()


async def store_stage_output(factory, lease, stage, output):
    async with factory.begin() as db:
        job = await db.scalar(select(OutboxEvent).where(*ownership(lease)).with_for_update())
        if job is None:
            raise LeaseLost()
        existing = job.stage_state.get(stage)
        accepted = {"status": "accepted", "output": output}
        if existing is not None and existing != accepted:
            raise StageConflict()
        state = {**job.stage_state, stage: accepted}
        changed = await db.scalar(update(OutboxEvent).where(*ownership(lease)).values(stage_state=state, updated_at=func.clock_timestamp()).returning(OutboxEvent.id))
        if changed is None:
            raise LeaseLost()


async def complete(factory, lease, apply):
    async with factory.begin() as db:
        await lock_workspace(db, lease.agency_id, task_id=lease.task_id)
        job = await db.scalar(select(OutboxEvent).where(*ownership(lease)).with_for_update())
        if job is None:
            raise LeaseLost()
        result = await apply(db, job)  # Database mutations only; all roll back on lost fencing.
        actor = job.payload.get("actor", {})
        db.add(AuditLog(agency_id=job.agency_id, service_actor="workflow_worker",
                       principal_user_id=uuid.UUID(actor["principal_id"]) if actor.get("principal_id") else None,
                       effective_user_id=uuid.UUID(actor["effective_user_id"]) if actor.get("effective_user_id") else None,
                       event_type="workflow.completed", correlation_id=job.id,
                       references_json={"job_id": str(job.id)}, details={"event_type": job.event_type}))
        await db.flush()
        changed = await db.scalar(update(OutboxEvent).where(*ownership(lease)).values(
            state="done", lease_token=None, lease_until=None, last_error_code=None,
            stage_state={**job.stage_state, "result": result}, updated_at=func.clock_timestamp()).returning(OutboxEvent.id))
        if changed is None:
            raise LeaseLost()


async def fail(factory, lease, code, *, held=False, max_attempts=3):
    async with factory.begin() as db:
        job = await db.scalar(select(OutboxEvent).where(*ownership(lease)).with_for_update())
        if job is None:
            raise LeaseLost()
        terminal = held or job.attempt_count >= max_attempts
        state = "held" if held else "failed" if terminal else "ready"
        changed = await db.scalar(update(OutboxEvent).where(*ownership(lease)).values(
            state=state, lease_token=None, lease_until=None, last_error_code=code,
            available_at=func.clock_timestamp()+timedelta(seconds=min(2**job.attempt_count,30)),
            updated_at=func.clock_timestamp()).returning(OutboxEvent.id))
        if changed is None:
            raise LeaseLost()
