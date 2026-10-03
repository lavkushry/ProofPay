"""Workflow worker with provider credentials but no financial database grants."""

import asyncio
import signal
import uuid

from sqlalchemy import func, select, update
from pydantic import ValidationError

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal, engine
from backend.app.errors import APIError
from backend.app.models import AIInteraction, Agency, Brief, BriefRevision, Compilation, DeliveryTask, DemoRun, FixtureManifest, MandateVersion, OutboxEvent
from backend.app.schemas.api_schemas import CheckProposal
from backend.app.services.commands import canonical_digest
from backend.app.services.catalog import validated_snapshot
from backend.app.services.compiler import CompilerError, compilation_input, compile_revision, provider_config, validate_proposal
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


async def apply_compile(db, job):
    accepted = job.stage_state.get("compile", {}).get("output")
    if not isinstance(accepted, dict):
        raise APIError(409, "STALE_COMPILATION", "Compilation output is unavailable.")
    revision_id = uuid.UUID(job.payload["revision_id"])
    compilation = await db.scalar(select(Compilation).where(
        Compilation.agency_id==job.agency_id, Compilation.job_id==job.id,
        Compilation.brief_revision_id==revision_id).with_for_update())
    revision = await db.scalar(select(BriefRevision).where(
        BriefRevision.agency_id==job.agency_id, BriefRevision.id==revision_id))
    if compilation is None or revision is None or revision.digest != job.payload.get("revision_digest"):
        raise APIError(409, "STALE_REVISION", "Compilation lineage is unavailable.")
    proposal = accepted.get("proposal")
    manifest = await db.scalar(select(FixtureManifest).where(FixtureManifest.agency_id==job.agency_id,
        FixtureManifest.id==revision.manifest_id))
    if manifest is None or str(manifest.id) != job.payload.get("manifest_id"):
        raise APIError(409, "STALE_COMPILATION", "Compilation manifest is unavailable.")
    contract = validated_snapshot(manifest)
    _prompt, digest = compilation_input(contract, revision)
    try:
        checked = CheckProposal.model_validate(proposal, strict=True)
        if checked.model_dump(mode="json") != proposal:
            raise ValueError("Incomplete compiler proposal")
        status, _ = validate_proposal(checked, contract, revision.family)
    except (ValidationError, TypeError, ValueError):
        raise APIError(409, "STALE_COMPILATION", "Compilation output is invalid.") from None
    if (accepted.get("input_digest") != digest or accepted.get("output_digest") != canonical_digest(proposal)
        or accepted.get("status") != status):
        raise APIError(409, "STALE_COMPILATION", "Compilation output does not match its inputs.")
    current = await current_compile_source(db, job)
    interaction = AIInteraction(
        id=uuid.uuid4(), agency_id=job.agency_id, job_id=job.id, stage="compiler",
        brief_revision_id=revision.id, model_ref=accepted["provider"] + ":" + accepted["model"],
        prompt_version=accepted["prompt_version"], schema_version=accepted["schema_version"],
        input_digest=accepted["input_digest"],
        input_refs={"brief_revision_id": str(revision.id), "manifest_id": job.payload["manifest_id"]},
        output=proposal, output_digest=accepted["output_digest"],
        validated=accepted["status"] == "ready", error_code=None if accepted["status"] == "ready" else "AMBIGUOUS",
        usage=accepted.get("usage"),
    )
    db.add(interaction)
    await db.flush()
    compilation.interaction_id = interaction.id
    compilation.status = status if current is not None else "stale"
    compilation.proposal = proposal
    return {"compilation_id": str(compilation.id), "status": compilation.status,
            "interaction_id": str(interaction.id)}


async def current_compile_source(db, job):
    return (await db.execute(select(BriefRevision, FixtureManifest).join(Brief,
        (Brief.agency_id==BriefRevision.agency_id)&(Brief.id==BriefRevision.brief_id))
        .join(DeliveryTask, (DeliveryTask.agency_id==Brief.agency_id)&(DeliveryTask.brief_id==Brief.id))
        .join(Agency, Agency.id==Brief.agency_id)
        .join(DemoRun, (DemoRun.agency_id==Agency.id)&(DemoRun.id==Agency.current_demo_run_id))
        .join(FixtureManifest, (FixtureManifest.agency_id==BriefRevision.agency_id)&
              (FixtureManifest.id==BriefRevision.manifest_id))
        .where(BriefRevision.agency_id==job.agency_id, BriefRevision.id==uuid.UUID(job.payload["revision_id"]),
               BriefRevision.digest==job.payload["revision_digest"], Brief.current_revision_id==BriefRevision.id,
               Brief.id==uuid.UUID(job.payload["brief_id"]), DeliveryTask.id==job.task_id,
               DeliveryTask.demo_run_id==DemoRun.id, DemoRun.state=="active",
               FixtureManifest.id==uuid.UUID(job.payload["manifest_id"])))).first()


async def fenced_job(db, lease):
    job = await db.scalar(select(OutboxEvent).where(*outbox.ownership(lease)).with_for_update())
    if job is None:
        raise outbox.LeaseLost()
    return job


async def recheck_fence(db, lease):
    await db.flush()
    if await db.scalar(select(OutboxEvent.id).where(*outbox.ownership(lease))) is None:
        raise outbox.LeaseLost()


async def _compile_input(factory, lease):
    async with factory() as db:
        row = await current_compile_source(db, lease)
        if row is None:
            raise APIError(409, "STALE_REVISION", "Compilation lineage is unavailable.")
        revision, manifest = row
        return revision, validated_snapshot(manifest)


async def _mark_compilation_running(factory, lease):
    async with factory.begin() as db:
        await fenced_job(db, lease)
        await db.execute(update(Compilation).where(
            Compilation.agency_id==lease.agency_id, Compilation.job_id==lease.id,
            Compilation.status.in_(("queued", "failed"))).values(status="running"))
        await recheck_fence(db, lease)


async def _record_compile_failure(factory, lease, revision, contract, error):
    _prompt, input_digest = compilation_input(contract, revision)
    async with factory.begin() as db:
        await fenced_job(db, lease)
        interaction = AIInteraction(
            id=uuid.uuid4(), agency_id=lease.agency_id, job_id=lease.id, stage="compiler",
            brief_revision_id=revision.id, model_ref=settings.LLM_PROVIDER or "unconfigured",
            prompt_version=settings.COMPILER_PROMPT_VERSION, schema_version=settings.SCHEMA_VERSION,
            input_digest=input_digest,
            input_refs={"brief_revision_id": str(revision.id), "manifest_id": lease.payload["manifest_id"]},
            output=None, output_digest=None, validated=False, error_code=error.code, usage=None,
        )
        db.add(interaction)
        await db.execute(update(Compilation).where(
            Compilation.agency_id==lease.agency_id, Compilation.job_id==lease.id,
            Compilation.status=="running").values(status="failed"))
        await recheck_fence(db, lease)


async def _record_compile_start(factory, lease, revision, contract):
    config = provider_config()
    _prompt, input_digest = compilation_input(contract, revision)
    async with factory.begin() as db:
        await fenced_job(db, lease)
        if await current_compile_source(db, lease) is None:
            raise APIError(409, "STALE_REVISION", "Compilation inputs changed before model invocation.")
        calls = await db.scalar(select(func.count()).select_from(AIInteraction).where(
            AIInteraction.agency_id==lease.agency_id, AIInteraction.job_id==lease.id,
            AIInteraction.stage=="compiler", AIInteraction.error_code=="STARTED"))
        if calls >= settings.LLM_MAX_CALLS_PER_STAGE:
            raise CompilerError("CALL_BUDGET_EXCEEDED")
        db.add(AIInteraction(
            id=uuid.uuid4(), agency_id=lease.agency_id, job_id=lease.id, stage="compiler",
            brief_revision_id=revision.id, model_ref=config.name + ":" + config.model,
            prompt_version=settings.COMPILER_PROMPT_VERSION, schema_version=settings.SCHEMA_VERSION,
            input_digest=input_digest,
            input_refs={"brief_revision_id": str(revision.id), "manifest_id": lease.payload["manifest_id"]},
            output=None, output_digest=None, validated=False, error_code="STARTED", usage=None,
        ))
        await recheck_fence(db, lease)
    return config


async def process_compile(factory, lease):
    if "compile" not in lease.stage_state:
        await _mark_compilation_running(factory, lease)
        revision, contract = await _compile_input(factory, lease)
        try:
            config = await _record_compile_start(factory, lease, revision, contract)
            result = await compile_revision(contract, revision, config=config)
        except CompilerError as error:
            await _record_compile_failure(factory, lease, revision, contract, error)
            raise
        output = {
            "proposal": result.proposal.model_dump(mode="json"), "status": result.status,
            "provider": result.provider, "model": result.model, "prompt_version": result.prompt_version,
            "schema_version": result.schema_version, "input_digest": result.input_digest,
            "output_digest": result.output_digest, "usage": result.usage,
            "reasons": list(result.reasons),
        }
        await outbox.store_stage_output(factory, lease, "compile", output)
    await outbox.complete(factory, lease, apply_compile)


async def process_lease(factory, lease):
    if lease.event_type == "compile_requested":
        await process_compile(factory, lease)
        return
    if lease.event_type == "mandate_recorded":
        await outbox.complete(factory, lease, apply_mandate_recorded)
        return
    if lease.event_type != "brief_recorded":
        await outbox.fail(factory, lease, "UNSUPPORTED_JOB", held=True)
        return
    if "capture" not in lease.stage_state:
        await outbox.store_stage_output(factory, lease, "capture", {"brief_id": lease.payload["brief_id"]})
    await outbox.complete(factory, lease, apply_brief_recorded)


async def apply_mandate_recorded(db, job):
    version = await db.scalar(select(MandateVersion).where(MandateVersion.agency_id==job.agency_id,
        MandateVersion.id==uuid.UUID(job.payload["version_id"]), MandateVersion.task_id==job.task_id,
        MandateVersion.mandate_id==uuid.UUID(job.payload["mandate_id"])))
    if version is None:
        raise APIError(409, "STALE_MANDATE", "Recorded mandate lineage is unavailable.")
    return {"mandate_id": str(version.mandate_id), "version_id": str(version.id)}


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
    except CompilerError as error:
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
    print("Workflow worker started; model calls run only in leased compilation stages.", flush=True)
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
