"""Capture authority-free drafts; compilation/approval remain subsequent milestones."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.models import Agency, Brief, BriefRevision, Contractor, DeliveryTask, DemoRun, FixtureManifest, Mandate, PaymentObligation
from backend.app.schemas.commands import BriefCreate, BriefRevisionCreate, CompileRequest
from backend.app.schemas.briefs import BriefList, BriefResponse
from backend.app.schemas.compilations import CompilationAccepted, CompilationResponse
from backend.app.services.auth import Actor, require_csrf, require_owner, now
from backend.app.services.commands import CommandResult, canonical_digest, execute_command, idempotency_key
from backend.app.services.briefs import append_revision, brief_query, owned_brief, public_brief
from backend.app.services.catalog import current_manifest
from backend.app.services.pagination import decode_cursor, encode_cursor
from backend.app.services.compilations import by_id, enqueue, for_brief, latest

router = APIRouter(tags=["Briefs"])


@router.post("/api/briefs", status_code=201, response_model=BriefResponse, dependencies=[Depends(require_owner)])
async def create_brief(body: BriefCreate, request: Request, actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    async def authorize(database, current):
        if current.role != "owner":
            raise APIError(403, "FORBIDDEN", "Only the owner persona may capture briefs.")

    async def mutate(database, current):
        agency = await database.get(Agency, current.agency_id)
        run = await database.scalar(select(DemoRun).where(DemoRun.agency_id==current.agency_id, DemoRun.id==agency.current_demo_run_id, DemoRun.state=="active"))
        manifest, _ = await current_manifest(database, current.agency_id)
        contractor = await database.scalar(select(Contractor).where(Contractor.agency_id==current.agency_id, Contractor.recipient_ref==body.terms.recipient_ref))
        if run is None or manifest is None or contractor is None:
            raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Trusted fixture catalog and active workspace must be configured before capturing a brief.")
        stamp = now()
        brief_id, revision_id, task_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        terms = body.terms.model_dump(mode="json")
        digest = canonical_digest({**body.model_dump(mode="json"), "manifest_digest": manifest.digest, "revision": 1})
        database.add(Brief(id=brief_id, agency_id=current.agency_id, created_by=current.effective_user_id, created_at=stamp))
        await database.flush()
        database.add(BriefRevision(id=revision_id, agency_id=current.agency_id, brief_id=brief_id, revision=1,
                                   title=body.title, body=body.text, family=body.family, manifest_id=manifest.id,
                                   proposed_terms=terms, digest=digest, created_at=stamp))
        await database.flush()
        brief = await database.get(Brief, brief_id)
        brief.current_revision_id = revision_id
        database.add(DeliveryTask(id=task_id, agency_id=current.agency_id, demo_run_id=run.id, brief_id=brief_id, state="brief_captured", updated_at=stamp))
        await database.flush()
        database.add(Mandate(agency_id=current.agency_id, task_id=task_id))
        database.add(PaymentObligation(agency_id=current.agency_id, task_id=task_id))
        public = {"id": str(brief_id), "task_id": str(task_id), "revision_id": str(revision_id), "revision": 1,
                  "digest": digest, "title": body.title, "text": body.text, "family": body.family,
                  "fixture_ref": body.fixture_ref, "terms": terms, "created_at": stamp.isoformat(), "updated_at": stamp.isoformat()}
        return CommandResult(201, public, task_id, "brief_recorded", {"brief_id": str(brief_id), "revision_id": str(revision_id)})

    status, result = await execute_command(db, actor, "create_brief", idempotency_key(request), body,
                                           request.state.request_id, authorize, mutate)
    return JSONResponse(status_code=status, content=result)


@router.get("/api/briefs", response_model=BriefList)
async def list_briefs(actor: Actor = Depends(require_owner), db: AsyncSession = Depends(get_db),
                      cursor: str | None = Query(default=None, max_length=256), limit: int = Query(default=50, ge=1, le=100)):
    query = brief_query(actor.agency_id)
    if cursor is not None:
        stamp, identifier = decode_cursor(cursor, actor.agency_id)
        query = query.where(or_(Brief.created_at < stamp, and_(Brief.created_at==stamp, Brief.id < identifier)))
    rows = (await db.execute(query.order_by(Brief.created_at.desc(), Brief.id.desc()).limit(limit+1))).all()
    more = len(rows) > limit
    rows = rows[:limit]
    following = encode_cursor(actor.agency_id, rows[-1][0].created_at, rows[-1][0].id) if more else None
    return {"items": [public_brief(row) for row in rows], "next_cursor": following}


@router.get("/api/briefs/{brief_id}", response_model=BriefResponse)
async def get_brief(brief_id: uuid.UUID, actor: Actor = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    return public_brief(await owned_brief(db, actor, brief_id))


@router.post("/api/briefs/{brief_id}/compile", status_code=202, response_model=CompilationAccepted,
             dependencies=[Depends(require_owner)])
async def compile_brief(brief_id: uuid.UUID, body: CompileRequest, request: Request,
                        actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    status, result = await enqueue(db, actor, brief_id, body, request.state.request_id, idempotency_key(request))
    return JSONResponse(status_code=status, content=result)


@router.get("/api/briefs/{brief_id}/compilation", response_model=CompilationResponse)
async def get_compilation(brief_id: uuid.UUID, actor: Actor = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    compilation, brief, revision = await latest(db, actor, brief_id)
    return {"id": compilation.id, "brief_id": brief.id, "revision_id": revision.id,
            "status": compilation.status, "proposal": compilation.proposal, "created_at": compilation.created_at}


@router.get("/api/briefs/{brief_id}/compilations", response_model=list[CompilationResponse])
async def list_compilations(brief_id: uuid.UUID, actor: Actor = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    rows = await for_brief(db, actor, brief_id)
    return [{"id": compilation.id, "brief_id": brief_id, "revision_id": revision.id,
             "status": compilation.status, "proposal": compilation.proposal, "created_at": compilation.created_at}
            for compilation, revision in rows]


@router.get("/api/compilations/{compilation_id}", response_model=CompilationResponse)
async def get_compilation_by_id(compilation_id: uuid.UUID, actor: Actor = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    compilation, brief, revision = await by_id(db, actor, compilation_id)
    return {"id": compilation.id, "brief_id": brief.id, "revision_id": revision.id,
            "status": compilation.status, "proposal": compilation.proposal, "created_at": compilation.created_at}


@router.post("/api/briefs/{brief_id}/revisions", status_code=201, response_model=BriefResponse,
             dependencies=[Depends(require_owner)])
async def revise_brief(brief_id: uuid.UUID, body: BriefRevisionCreate, request: Request,
                       actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    row = await owned_brief(db, actor, brief_id)
    task_id = row[2].id  # Copy identity before the command clears authentication reads.
    async def authorize(database, current):
        if current.role != "owner":
            raise APIError(403, "FORBIDDEN", "Only the owner persona may revise briefs.")
        await owned_brief(database, current, brief_id)
    async def mutate(database, current):
        return await append_revision(database, current, brief_id, body)
    canonical = {"brief_id": str(brief_id), **body.model_dump(mode="json")}
    status, result = await execute_command(db, actor, "revise_brief", idempotency_key(request), canonical,
        request.state.request_id, authorize, mutate, task_id=task_id)
    return JSONResponse(status_code=status, content=result)
