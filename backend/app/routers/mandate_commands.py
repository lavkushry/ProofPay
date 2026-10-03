import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.schemas.mandates import (
    ApproveRequest, MandateDraftCreate, MandateResponse, MandateVersionCreate, MandateVersionResponse,
)
from backend.app.services.auth import Actor, get_actor, require_csrf, require_owner
from backend.app.services.commands import execute_command, idempotency_key
from backend.app.services import mandates

router = APIRouter(prefix="/api/mandates", tags=["Mandates"])


@router.post("", status_code=201, response_model=MandateVersionResponse, dependencies=[Depends(require_owner)])
async def create_mandate(body: MandateDraftCreate, request: Request,
                         actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    async def authorize(database, current):
        if current.role != "owner":
            raise APIError(403, "FORBIDDEN", "Only the owner may draft mandates.")
        await mandates.mandate_for_task(database, current, body.task_id)
    async def mutate(database, current):
        mandate, task = await mandates.mandate_for_task(database, current, body.task_id)
        return await mandates.create_draft(database, current, mandate, task, body, first=True)
    status, result = await execute_command(db, actor, "create_mandate", idempotency_key(request), body,
        request.state.request_id, authorize, mutate, task_id=body.task_id)
    return JSONResponse(status_code=status, content=result)


@router.get("/{mandate_id}", response_model=MandateResponse)
async def get_mandate(mandate_id: uuid.UUID, actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    return await mandates.read_mandate(db, actor, mandate_id)


@router.get("/{mandate_id}/versions/{version_id}", response_model=MandateVersionResponse)
async def get_version(mandate_id: uuid.UUID, version_id: uuid.UUID,
                      actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    return await mandates.read_version(db, actor, mandate_id, version_id)


async def version_command(db, actor, mandate_id, request, body, operation, mutation, version_id=None):
    _, task = await mandates.owned_mandate(db, actor, mandate_id)
    task_id = task.id
    async def authorize(database, current):
        await mandates.owned_mandate(database, current, mandate_id)
    async def mutate(database, current):
        mandate, task = await mandates.owned_mandate(database, current, mandate_id)
        if version_id is None:
            return await mutation(database, current, mandate, task, body)
        return await mutation(database, current, mandate, task, version_id, body)
    canonical = {"mandate_id": str(mandate_id), **body.model_dump(mode="json")}
    if version_id is not None:
        canonical["version_id"] = str(version_id)
    status, result = await execute_command(db, actor, operation, idempotency_key(request), canonical,
        request.state.request_id, authorize, mutate, task_id=task_id)
    return JSONResponse(status_code=status, content=result)


@router.post("/{mandate_id}/versions", status_code=201, response_model=MandateVersionResponse,
             dependencies=[Depends(require_owner)])
async def create_version(mandate_id: uuid.UUID, body: MandateVersionCreate, request: Request,
                         actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    return await version_command(db, actor, mandate_id, request, body, "create_mandate_version", mandates.create_draft)


@router.post("/{mandate_id}/versions/{version_id}/approve", response_model=MandateVersionResponse,
             dependencies=[Depends(require_owner)])
async def approve_version(mandate_id: uuid.UUID, version_id: uuid.UUID, body: ApproveRequest, request: Request,
                          actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    return await version_command(db, actor, mandate_id, request, body, "approve_mandate", mandates.approve, version_id)
