from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Contractor
from backend.app.services.auth import Actor, get_actor, require_owner
from backend.app.services.catalog import current_manifest

router = APIRouter(prefix="/api/v1/catalog", tags=["Catalog"])


async def _families(db, actor):
    _manifest, contract = await current_manifest(db, actor.agency_id)
    return [family.model_dump(mode="json") for family in contract.families]


@router.get("/families")
async def list_supported_families(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    return await _families(db, actor)


@router.get("/recipients", dependencies=[Depends(require_owner)])
async def list_contractors(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Contractor).where(Contractor.agency_id==actor.agency_id)
             .order_by(Contractor.recipient_ref))).scalars()
    return [{"id": str(item.id), "recipient_ref": item.recipient_ref,
             "display_name": item.display_name, "environment": "sandbox"} for item in rows]


@router.get("/artifacts")
async def list_artifacts(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    _manifest, contract = await current_manifest(db, actor.agency_id)
    return [{"artifact_ref": item.artifact_ref, "family": item.family, "label": item.label,
             "digest": item.digest, "relative_path": item.relative_path} for item in contract.artifacts]
