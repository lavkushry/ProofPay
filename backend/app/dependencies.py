from fastapi import Depends, Request

from backend.app.errors import APIError
from backend.app.services.auth import Actor, require_csrf
from backend.app.services.commands import idempotency_key


async def require_workflow(request: Request, actor: Actor = Depends(require_csrf)):
    """Keep unfinished prototype mutations out of executed business records."""
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if "/judge/" in request.url.path and not actor.is_judge:
            raise APIError(403, "FORBIDDEN", "This action requires the original judge principal.")
        if ("/briefs" in request.url.path or "/mandates" in request.url.path) and actor.role != "owner":
            raise APIError(403, "FORBIDDEN", "This action requires the owner persona.")
        idempotency_key(request)
        raise APIError(503, "WORKFLOW_UNAVAILABLE", "This workflow is awaiting trusted verification and guarded payment processing. No work or payment was created.")
