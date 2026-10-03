"""One agency advisory lock; row order matches the payout transaction protocol."""

from sqlalchemy import select, text

from backend.app.errors import APIError
from backend.app.models import Agency, DeliveryTask, MandateVersion, PaymentAttempt, PaymentObligation, PayoutItem


async def lock_workspace(db, agency_id, *, task_id=None, obligation_id=None, mandate_version_id=None, attempt_id=None):
    if db.bind.dialect.name != "postgresql":
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Durable domain commands require PostgreSQL.")
    key = await db.scalar(select(Agency.advisory_lock_key).where(Agency.id==agency_id))
    if key is None:
        raise APIError(404, "NOT_FOUND", "Workspace not found.")
    if not await db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):
        raise APIError(409, "WORKSPACE_BUSY", "Workspace is busy; retry the same command.", retryable=True)
    agency = await db.scalar(select(Agency).where(Agency.id==agency_id).with_for_update())
    # Agency allowance → task/obligation → mandate → attempt → item projection.
    for model, identifier in ((DeliveryTask, task_id), (PaymentObligation, obligation_id),
                              (MandateVersion, mandate_version_id), (PaymentAttempt, attempt_id)):
        if identifier is not None:
            row = await db.scalar(select(model).where(model.agency_id==agency_id, model.id==identifier).with_for_update())
            if row is None:
                raise APIError(404, "NOT_FOUND", "Command resource not found.")
    if attempt_id is not None:
        await db.execute(select(PayoutItem).where(PayoutItem.agency_id==agency_id, PayoutItem.attempt_id==attempt_id).with_for_update())
    return agency
