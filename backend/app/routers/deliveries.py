from fastapi import APIRouter, Depends

from backend.app.dependencies import require_workflow
from backend.app.schemas.api_schemas import DeliveryResponse, DeliverySubmitRequest

router = APIRouter(prefix="/api/v1/deliveries", tags=["Deliveries"])


@router.post(
    "/submit", response_model=DeliveryResponse, dependencies=[Depends(require_workflow)]
)
async def submit_delivery(req: DeliverySubmitRequest):
    """Reserved for the durable verification workflow; currently returns 503."""
    raise RuntimeError("Workflow guard must run before delivery submission")
