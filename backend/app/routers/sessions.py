import hmac

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.models import AuditLog, SessionModel, User
from backend.app.schemas.session import RoleSwitch, SessionCreate, SessionResponse
from backend.app.services.auth import (
    COOKIE, Actor, auth_configuration, check_origin, cookie_digest, get_actor,
    new_session, now, persona_user, require_csrf, require_judge, resolve_actor,
    session_response, set_cookie,
)

router = APIRouter(tags=["Sessions"])


def audit(db, request, actor, event, session_id):
    db.add(AuditLog(agency_id=actor.agency_id, principal_user_id=actor.principal_id,
                    effective_user_id=actor.effective_user_id, event_type=event,
                    correlation_id=request.state.request_id,
                    references_json={"session_id": str(session_id)}, details={}))


@router.post("/api/session", response_model=SessionResponse, status_code=201)
async def create_session(body: SessionCreate, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_origin(request)
    _, codes = auth_configuration()
    grant = next((name for name, code in codes.items() if code and hmac.compare_digest(code.encode(), body.access_code.encode())), None)
    if grant is None:
        raise APIError(401, "UNAUTHORIZED", "Access code is invalid.")
    if grant != "judge" and grant != body.persona:
        raise APIError(403, "FORBIDDEN", "This access code does not permit that persona.")
    effective = await persona_user(db, settings.DEFAULT_AGENCY_ID, body.persona)
    principal = effective
    if grant == "judge":
        principal = await db.scalar(select(User).where(User.agency_id==effective.agency_id, User.role=="judge"))
        if principal is None:
            raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Judge identity is unavailable.")
    old_cookie = request.cookies.get(COOKIE)
    if old_cookie:
        old = await db.scalar(select(SessionModel).where(SessionModel.cookie_hash==cookie_digest(old_cookie)).with_for_update())
        if old is not None:
            old.revoked_at = now()
    session, cookie = new_session(effective.agency_id, principal.id, effective.id, grant=="judge")
    db.add(session)
    await db.flush()
    actor = await resolve_actor(db, session)
    audit(db, request, actor, "session.created", session.id)
    await db.commit()
    set_cookie(response, cookie)
    return session_response(actor, session)


@router.get("/api/session", response_model=SessionResponse)
async def get_session(request: Request, actor: Actor = Depends(get_actor)):
    return session_response(actor, request.state.session)


@router.delete("/api/session", status_code=204)
async def delete_session(request: Request, response: Response, actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(SessionModel).where(SessionModel.id==actor.session_id).with_for_update().execution_options(populate_existing=True))
    await resolve_actor(db, session)
    session.revoked_at = now()
    audit(db, request, actor, "session.revoked", session.id)
    await db.commit()
    response.delete_cookie(COOKIE, path="/", secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite="lax")


@router.post("/api/judge/role", response_model=SessionResponse, dependencies=[Depends(require_judge)])
async def switch_role(body: RoleSwitch, request: Request, response: Response, actor: Actor = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    old = await db.scalar(select(SessionModel).where(SessionModel.id==actor.session_id).with_for_update().execution_options(populate_existing=True))
    await resolve_actor(db, old)
    effective = await persona_user(db, actor.agency_id, body.persona)
    session, cookie = new_session(actor.agency_id, actor.principal_id, effective.id, True, old.expires_at)
    old.revoked_at = now()
    db.add(session)
    await db.flush()
    rotated = await resolve_actor(db, session)
    audit(db, request, rotated, "session.persona_changed", session.id)
    await db.commit()
    set_cookie(response, cookie)
    return session_response(rotated, session)
