import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.schemas.commands import DeliveryCreate
from backend.app.services.auth import Actor, authorize_task, require_csrf
from backend.app.services.commands import execute_command, idempotency_key

router = APIRouter(tags=["Deliveries"])


@router.post("/api/tasks/{task_id}/deliveries")
@router.post("/api/contractor/tasks/{task_id}/deliveries")
async def submit_delivery(task_id: uuid.UUID, body: DeliveryCreate, request: Request,
                          actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    async def authorize(database, current):
        await authorize_task(database, current, task_id)

    async def mutate(database, current):
        raise APIError(503, "WORKFLOW_UNAVAILABLE", "Delivery verification is awaiting implementation. No work or payment was created.")

    # Both aliases share the identical validated body/target and command family.
    canonical = {"task_id": str(task_id), **body.model_dump(mode="json")}
    status, result = await execute_command(db, actor, "submit_delivery", idempotency_key(request), canonical,
                                           request.state.request_id, authorize, mutate, task_id=task_id)
    return JSONResponse(status_code=status, content=result)
