"""Read immutable revision projections and append drafts without changing authority."""

import uuid

from sqlalchemy import select

from backend.app.errors import APIError
from backend.app.models import Brief, BriefRevision, Contractor, DeliveryTask, DemoRun, FixtureManifest
from backend.app.services.auth import now
from backend.app.services.catalog import validated_snapshot
from backend.app.services.commands import CommandResult, canonical_digest


def brief_query(agency_id):
    return (select(Brief, BriefRevision, DeliveryTask, FixtureManifest)
        .join(BriefRevision, (BriefRevision.agency_id==Brief.agency_id)&(BriefRevision.id==Brief.current_revision_id))
        .join(DeliveryTask, (DeliveryTask.agency_id==Brief.agency_id)&(DeliveryTask.brief_id==Brief.id))
        .join(FixtureManifest, (FixtureManifest.agency_id==BriefRevision.agency_id)&(FixtureManifest.id==BriefRevision.manifest_id))
        .where(Brief.agency_id==agency_id))


async def owned_brief(db, actor, brief_id):
    row = (await db.execute(brief_query(actor.agency_id).where(Brief.id==brief_id))).one_or_none()
    if row is None:
        raise APIError(404, "NOT_FOUND", "Brief not found.")
    return row


def public_brief(row):
    brief, revision, task, manifest = row
    return {"id": str(brief.id), "task_id": str(task.id), "revision_id": str(revision.id),
        "revision": revision.revision, "digest": revision.digest, "title": revision.title,
        "text": revision.body, "family": revision.family, "fixture_ref": manifest.fixture_ref,
        "terms": revision.proposed_terms, "created_at": brief.created_at.isoformat(),
        "updated_at": revision.created_at.isoformat()}


def revision_digest(body, manifest, number):
    values = body.model_dump(mode="json")
    values.pop("expected_revision", None)
    return canonical_digest({**values, "fixture_ref": manifest.fixture_ref,
        "manifest_digest": manifest.digest, "revision": number})


async def append_revision(db, actor, brief_id, body):
    brief, previous, task, manifest = await owned_brief(db, actor, brief_id)
    if previous.revision != body.expected_revision:
        raise APIError(409, "STALE_REVISION", "The brief has a newer revision. Reload it before saving.")
    run = await db.get(DemoRun, task.demo_run_id)
    if run is None or run.agency_id != actor.agency_id or run.state != "active":
        raise APIError(409, "STALE_REVISION", "This brief belongs to an archived workspace run.")
    validated_snapshot(manifest)
    contractor = await db.scalar(select(Contractor.id).where(Contractor.agency_id==actor.agency_id,
        Contractor.recipient_ref==body.terms.recipient_ref))
    if contractor is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "The proposed contractor is unavailable.")
    stamp = now()
    revision = BriefRevision(id=uuid.uuid4(), agency_id=actor.agency_id, brief_id=brief.id,
        revision=previous.revision+1, title=body.title, body=body.text, family=body.family,
        manifest_id=previous.manifest_id, proposed_terms=body.terms.model_dump(mode="json"),
        digest=revision_digest(body, manifest, previous.revision+1), created_at=stamp)
    db.add(revision)
    await db.flush()
    brief.current_revision_id = revision.id
    task.version += 1
    task.updated_at = stamp
    # Existing mandate/delivery/obligation authority remains pinned to its source.
    return CommandResult(201, public_brief((brief, revision, task, manifest)), task.id,
        "brief_recorded", {"brief_id": str(brief.id), "revision_id": str(revision.id)})
