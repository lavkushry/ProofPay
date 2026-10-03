"""Workflow worker with no model/provider credentials or financial database grants."""

import asyncio
import signal
import uuid

from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal, engine
from backend.app.errors import APIError
from backend.app.models import Brief, BriefRevision, DeliveryTask
from backend.app.services import outbox


async def apply_brief_recorded(db, job):
    brief_id, revision_id = uuid.UUID(job.payload["brief_id"]), uuid.UUID(job.payload["revision_id"])
    revision = await db.scalar(select(BriefRevision)
        .join(Brief, (Brief.agency_id==BriefRevision.agency_id)&(Brief.id==BriefRevision.brief_id))
        .join(DeliveryTask, (DeliveryTask.agency_id==Brief.agency_id)&(DeliveryTask.brief_id==Brief.id))
        .where(BriefRevision.agency_id==job.agency_id, BriefRevision.id==revision_id,
               Brief.id==brief_id, DeliveryTask.id==job.task_id))
    if revision is None:
        raise APIError(409, "STALE_REVISION", "Recorded brief lineage is unavailable.")
    # Records durable capture only; no inferred checks, review or payment outcome.
    return {"resource_id": str(brief_id), "hold_reasons": []}


async def process_lease(factory, lease):
    if lease.event_type != "brief_recorded":
        await outbox.fail(factory, lease, "UNSUPPORTED_JOB", held=True)
        return
    if "capture" not in lease.stage_state:
        await outbox.store_stage_output(factory, lease, "capture", {"brief_id": lease.payload["brief_id"]})
    await outbox.complete(factory, lease, apply_brief_recorded)


async def heartbeat_loop(factory, lease):
    while True:
        await asyncio.sleep(settings.WORKER_HEARTBEAT_SECONDS)
        await outbox.heartbeat(factory, lease, lease_seconds=settings.WORKER_LEASE_SECONDS)


async def run_once(factory=AsyncSessionLocal):
    lease = await outbox.claim(factory, lease_seconds=settings.WORKER_LEASE_SECONDS, max_attempts=settings.WORKER_MAX_ATTEMPTS)
    if lease is None:
        return False
    heartbeat_task = asyncio.create_task(heartbeat_loop(factory, lease))
    work = asyncio.create_task(process_lease(factory, lease))
    try:
        done, _ = await asyncio.wait({work, heartbeat_task}, return_when=asyncio.FIRST_COMPLETED)
        if heartbeat_task in done:
            await heartbeat_task  # Lease loss cancels work; it never authorizes completion.
        await work
    except outbox.LeaseLost:
        pass
    except APIError as error:
        try:
            await outbox.fail(factory, lease, error.code, held=not error.retryable, max_attempts=settings.WORKER_MAX_ATTEMPTS)
        except outbox.LeaseLost:
            pass
    except Exception:
        # Never print exception strings, source bodies, tokens or DB parameters.
        try:
            await outbox.fail(factory, lease, "WORKER_ERROR", max_attempts=settings.WORKER_MAX_ATTEMPTS)
        except outbox.LeaseLost:
            pass
    finally:
        heartbeat_task.cancel()
        work.cancel()
        await asyncio.gather(heartbeat_task, work, return_exceptions=True)
    return True


async def main():
    if settings.WORKER_HEARTBEAT_SECONDS * 2 >= settings.WORKER_LEASE_SECONDS:
        raise SystemExit("Worker heartbeat must be shorter than half its lease.")
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(name, stopping.set)
    print("Workflow worker started; model, verification and financial handlers remain unavailable.", flush=True)
    try:
        while not stopping.is_set():
            if not await run_once():
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=1)
                except TimeoutError:
                    pass
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
