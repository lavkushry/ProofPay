from fastapi import APIRouter, Depends

from backend.app.dependencies import require_workflow

router = APIRouter(prefix="/api/v1/briefs", tags=["Briefs"])


@router.post("", dependencies=[Depends(require_workflow)])
async def create_and_compile_brief():
    """Transitional combined compiler route; real inference is implemented in M2."""
    raise RuntimeError("Workflow guard must run before compilation")
