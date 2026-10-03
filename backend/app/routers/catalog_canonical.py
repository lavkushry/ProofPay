from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import ArtifactVersion, Contractor, FixtureManifest
from backend.app.services.auth import Actor, get_actor, require_owner

router = APIRouter(tags=["Catalog"])


@router.get("/api/contractors", dependencies=[Depends(require_owner)])
async def contractors(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Contractor).where(Contractor.agency_id==actor.agency_id)
             .order_by(Contractor.recipient_ref))).scalars()
    return [{"id": str(item.id), "recipient_ref": item.recipient_ref,
             "display_name": item.display_name, "environment": "sandbox"} for item in rows]


@router.get("/api/fixtures/versions")
async def fixture_versions(actor: Actor = Depends(get_actor), db: AsyncSession = Depends(get_db)):
    query = (select(ArtifactVersion, FixtureManifest.fixture_ref, FixtureManifest.version)
             .join(FixtureManifest, (FixtureManifest.agency_id==ArtifactVersion.agency_id)&(FixtureManifest.id==ArtifactVersion.manifest_id))
             .where(ArtifactVersion.agency_id==actor.agency_id)
             .order_by(ArtifactVersion.family, ArtifactVersion.artifact_ref))
    rows = (await db.execute(query)).all()
    return [{"id": str(artifact.id), "fixture_ref": fixture_ref, "version": version,
             "artifact_ref": artifact.artifact_ref, "family": artifact.family,
             "digest": artifact.digest, "relative_path": artifact.relative_path} for artifact, fixture_ref, version in rows]
