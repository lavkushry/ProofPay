import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.schemas.verification import RunnerClaim, RunnerCompletion, RunnerCompletionResult, RunnerHeartbeat, RunnerJob
from backend.app.services.runner_auth import require_runner
from backend.app.services import runner_jobs
from fixture_contract.registry import decode_json

router = APIRouter(prefix="/internal/runner/jobs", tags=["Internal Runner"])


@router.post("/claim", response_model=RunnerJob)
async def claim(body: RunnerClaim, agency_id: uuid.UUID = Depends(require_runner), db: AsyncSession = Depends(get_db)):
    job = await runner_jobs.claim(db, agency_id, body)
    return Response(status_code=204) if job is None else job


@router.post("/{job_id}/heartbeat", status_code=204)
async def heartbeat(job_id: uuid.UUID, body: RunnerHeartbeat, agency_id: uuid.UUID = Depends(require_runner),
                    db: AsyncSession = Depends(get_db)):
    await runner_jobs.heartbeat(db, agency_id, job_id, body)
    return Response(status_code=204)


async def bounded_completion(request: Request, agency_id: uuid.UUID = Depends(require_runner)):
    data = bytearray()
    async for part in request.stream():
        if len(data)+len(part)>3145728:
            raise APIError(413, "INVALID_EVIDENCE", "Runner completion exceeds 3 MiB.")
        data.extend(part)
    try:
        return RunnerCompletion.model_validate(decode_json(bytes(data)))
    except (ValueError, TypeError, ValidationError):
        raise APIError(422, "INVALID_EVIDENCE", "Runner completion is malformed.") from None


@router.post("/{job_id}/complete", response_model=RunnerCompletionResult)
async def complete(job_id: uuid.UUID, request: Request, body: RunnerCompletion = Depends(bounded_completion),
                   agency_id: uuid.UUID = Depends(require_runner), db: AsyncSession = Depends(get_db)):
    return await runner_jobs.complete(db, agency_id, job_id, body, request.state.request_id)
