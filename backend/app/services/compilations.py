"""Durable compilation command enqueueing and owner-scoped projections."""

import uuid

from sqlalchemy import select

from backend.app.errors import APIError
from backend.app.models import AuditLog, Brief, BriefRevision, CommandReceipt, Compilation, OutboxEvent
from backend.app.services.auth import reauthorize
from backend.app.services.briefs import owned_brief
from backend.app.services.commands import canonical_digest, receipt_query, replay
from backend.app.services.locking import lock_workspace


async def enqueue(db, actor, brief_id, request, correlation_id, key):
    digest = canonical_digest({"brief_id": str(brief_id), **request.model_dump(mode="json")})
    await db.rollback()
    async with db.begin():
        await reauthorize(db, actor)
        receipt = await db.scalar(receipt_query(actor, "compile_brief", key))
        if receipt is not None:
            return replay(receipt, digest)
        await lock_workspace(db, actor.agency_id, task_id=None)
        await reauthorize(db, actor)
        row = await owned_brief(db, actor, brief_id)
        brief, revision, task, manifest = row
        if revision.revision != request.expected_revision or revision.digest != request.expected_digest:
            raise APIError(409, "STALE_REVISION", "The brief changed; reload it before compiling.")
        existing = await db.scalar(select(Compilation).where(
            Compilation.agency_id==actor.agency_id,
            Compilation.brief_revision_id==revision.id,
            Compilation.status.in_(("queued", "running", "ready", "ambiguous")),
        ).order_by(Compilation.created_at.desc()).limit(1))
        if existing is not None:
            raise APIError(409, "COMPILATION_EXISTS", "This brief revision already has a compilation.")
        job_id, compilation_id, command_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        job = OutboxEvent(id=job_id, agency_id=actor.agency_id, task_id=task.id,
            event_type="compile_requested", dedup_key=f"command:{command_id}",
            payload={"brief_id": str(brief.id), "revision_id": str(revision.id),
                     "revision_digest": revision.digest, "manifest_id": str(manifest.id),
                     "actor": {"principal_id": str(actor.principal_id), "effective_user_id": str(actor.effective_user_id)}})
        db.add(job)
        await db.flush()
        compilation = Compilation(id=compilation_id, agency_id=actor.agency_id,
            brief_revision_id=revision.id, job_id=job.id, status="queued")
        db.add(compilation)
        response = {"compilation_id": str(compilation.id), "job_id": str(job.id), "brief_id": str(brief.id),
                    "revision_id": str(revision.id), "revision": revision.revision, "digest": revision.digest, "status": "queued"}
        db.add(AuditLog(agency_id=actor.agency_id, principal_user_id=actor.principal_id,
            effective_user_id=actor.effective_user_id, event_type="command.compile_brief",
            correlation_id=correlation_id, references_json={"command_id": str(command_id), "job_id": str(job.id), "compilation_id": str(compilation.id)},
            details={"request_digest": digest}))
        db.add(CommandReceipt(
            id=command_id, agency_id=actor.agency_id, principal_user_id=actor.principal_id,
            effective_user_id=actor.effective_user_id, operation="compile_brief", idempotency_key=key,
            request_digest=digest, http_status=202, response=response))
        await db.flush()
        return 202, response


async def latest(db, actor, brief_id):
    row = await owned_brief(db, actor, brief_id)
    brief, revision, _task, _manifest = row
    compilation = await db.scalar(select(Compilation).where(
        Compilation.agency_id==actor.agency_id, Compilation.brief_revision_id==revision.id
    ).order_by(Compilation.created_at.desc()).limit(1))
    if compilation is None:
        raise APIError(404, "NOT_FOUND", "No compilation exists for this brief revision.")
    return compilation, brief, revision


async def for_brief(db, actor, brief_id):
    await owned_brief(db, actor, brief_id)
    rows = (await db.execute(select(Compilation, BriefRevision).join(
        BriefRevision, (BriefRevision.agency_id==Compilation.agency_id)&(BriefRevision.id==Compilation.brief_revision_id)
    ).where(Compilation.agency_id==actor.agency_id, BriefRevision.brief_id==brief_id)
      .order_by(Compilation.created_at.desc()))).all()
    return [(compilation, revision) for compilation, revision in rows]


async def by_id(db, actor, compilation_id):
    row = (await db.execute(select(Compilation, Brief, BriefRevision).join(
        BriefRevision, (BriefRevision.agency_id==Compilation.agency_id)&(BriefRevision.id==Compilation.brief_revision_id)
    ).join(Brief, (Brief.agency_id==Compilation.agency_id)&(Brief.id==BriefRevision.brief_id))
        .where(Compilation.agency_id==actor.agency_id, Compilation.id==compilation_id))).one_or_none()
    if row is None:
        raise APIError(404, "NOT_FOUND", "Compilation not found.")
    return row
