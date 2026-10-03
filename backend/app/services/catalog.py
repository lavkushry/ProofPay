"""Immutable catalog import and agency-scoped trusted snapshot lookup."""

import uuid

from sqlalchemy import select

from backend.app.errors import APIError
from backend.app.models import ArtifactVersion, FixtureManifest
from fixture_contract.registry import CatalogIntegrityError, FixtureContract


async def seed_catalog(db, agency_id, contract):
    document = contract.model_dump(mode="json")
    manifest = await db.scalar(select(FixtureManifest).where(
        FixtureManifest.agency_id==agency_id, FixtureManifest.fixture_ref==contract.fixture_ref,
        FixtureManifest.version==contract.version))
    if manifest is None:
        manifest = FixtureManifest(id=uuid.uuid4(), agency_id=agency_id,
            fixture_ref=contract.fixture_ref, version=contract.version, digest=contract.digest, manifest=document)
        db.add(manifest)
        await db.flush()
    elif manifest.digest != contract.digest or manifest.manifest != document:
        raise CatalogIntegrityError("Existing fixture version differs; publish a new version instead of overwriting history")
    for artifact in contract.artifacts:
        existing = await db.scalar(select(ArtifactVersion).where(
            ArtifactVersion.agency_id==agency_id, ArtifactVersion.artifact_ref==artifact.artifact_ref))
        fields = {"manifest_id": manifest.id, "family": artifact.family,
                  "digest": artifact.digest, "relative_path": artifact.relative_path}
        if existing is None:
            db.add(ArtifactVersion(id=uuid.uuid4(), agency_id=agency_id,
                                  artifact_ref=artifact.artifact_ref, **fields))
        elif any(getattr(existing, key) != value for key, value in fields.items()):
            raise CatalogIntegrityError("Existing artifact differs; use a new immutable reference")
    await db.flush()
    return manifest


def validated_snapshot(manifest):
    try:
        contract = FixtureContract.model_validate(manifest.manifest)
        if contract.digest != manifest.digest or contract.version != manifest.version or contract.fixture_ref != manifest.fixture_ref:
            raise CatalogIntegrityError("Manifest digest or identity is inconsistent")
        return contract
    except ValueError:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Trusted fixture catalog is invalid or unavailable.") from None


async def current_manifest(db, agency_id):
    manifest = await db.scalar(select(FixtureManifest).where(FixtureManifest.agency_id==agency_id,
        FixtureManifest.fixture_ref=="checkout_fixture").order_by(FixtureManifest.version.desc()).limit(1))
    if manifest is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Trusted fixture catalog has not been configured.")
    return manifest, validated_snapshot(manifest)
