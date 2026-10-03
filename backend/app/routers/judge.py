import uuid

from fastapi import APIRouter, Depends

from backend.app.dependencies import require_workflow

router = APIRouter(prefix="/api/v1/judge", tags=["Judge"])


@router.post("/reset", dependencies=[Depends(require_workflow)])
async def reset_demo_workspace():
    """Reset remains held until retained history and truthful seed gates pass."""
    raise RuntimeError("Workflow guard must run before reset")


@router.post("/replay-task/{task_id}", dependencies=[Depends(require_workflow)])
async def replay_delivery(task_id: uuid.UUID):
    """Actual workflow replay is implemented with M7, after financial guards."""
    raise RuntimeError("Workflow guard must run before financial replay")
