"""Capture authority-free drafts; compilation/approval remain subsequent milestones."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.models import Agency, Brief, BriefRevision, Contractor, DeliveryTask, DemoRun, FixtureManifest, Mandate, PaymentObligation
from backend.app.schemas.commands import BriefCreate
from backend.app.services.auth import Actor, require_csrf, require_owner, now
from backend.app.services.commands import CommandResult, canonical_digest, execute_command, idempotency_key

router = APIRouter(tags=["Briefs"])


@router.post("/api/briefs", status_code=201, dependencies=[Depends(require_owner)])
async def create_brief(body: BriefCreate, request: Request, actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    async def authorize(database, current):
        if current.role != "owner":
            raise APIError(403, "FORBIDDEN", "Only the owner persona may capture briefs.")

    async def mutate(database, current):
        agency = await database.get(Agency, current.agency_id)
        run = await database.scalar(select(DemoRun).where(DemoRun.agency_id==current.agency_id, DemoRun.id==agency.current_demo_run_id, DemoRun.state=="active"))
        manifest = await database.scalar(select(FixtureManifest).where(FixtureManifest.agency_id==current.agency_id, FixtureManifest.fixture_ref==body.fixture_ref).order_by(FixtureManifest.version.desc()).limit(1))
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
