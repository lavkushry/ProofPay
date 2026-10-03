"""Opaque sessions and server-resolved principal/effective identities."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.errors import APIError
from backend.app.models import Contractor, DeliveryTask, Mandate, MandateVersion, SessionModel, User
from backend.app.schemas.session import SessionResponse

COOKIE = "proofpay_session"


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def cookie_digest(cookie):
    return hashlib.sha256(cookie.encode()).hexdigest()


def auth_configuration():
    key = settings.SESSION_CSRF_KEY.get_secret_value()
    codes = {
        "judge": settings.DEMO_JUDGE_ACCESS_CODE.get_secret_value(),
        "owner": settings.DEMO_OWNER_ACCESS_CODE.get_secret_value(),
        "contractor_maya": settings.DEMO_MAYA_ACCESS_CODE.get_secret_value(),
        "contractor_leo": settings.DEMO_LEO_ACCESS_CODE.get_secret_value(),
    }
    active = [code for code in codes.values() if code]
    if len(key) < 32 or not active or len(active) != len(set(active)):
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Workspace access is not configured.")
    if not settings.SESSION_COOKIE_SECURE and settings.ENVIRONMENT not in {"development", "test"}:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "Secure session cookies are required.")
    return key, codes


def csrf_token(session):
    key, _ = auth_configuration()
    return hmac.new(key.encode(), f"{session.id}:{session.csrf_nonce}".encode(), hashlib.sha256).hexdigest()


def check_origin(request):
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.CORS_ORIGINS:
        raise APIError(403, "FORBIDDEN", "Request origin is not permitted.")
    if origin is None and request.headers.get("sec-fetch-site") == "cross-site":
        raise APIError(403, "FORBIDDEN", "Request origin is required.")


@dataclass(frozen=True)
class Actor:
    session_id: uuid.UUID
    agency_id: uuid.UUID
    principal_id: uuid.UUID
    effective_user_id: uuid.UUID
    role: str
    recipient_ref: str | None
    is_judge: bool


async def resolve_actor(db, session):
    if session is None or session.revoked_at is not None or aware(session.expires_at) <= now():
        raise APIError(401, "UNAUTHORIZED", "A current workspace session is required.")
    principal = await db.scalar(select(User).where(User.id==session.principal_user_id, User.agency_id==session.agency_id))
    effective = await db.scalar(select(User).where(User.id==session.effective_user_id, User.agency_id==session.agency_id))
    if principal is None or effective is None or effective.role not in {"owner", "contractor"}:
        raise APIError(401, "UNAUTHORIZED", "Session identity is unavailable.")
    if session.is_judge != (principal.role == "judge") or (not session.is_judge and principal.id != effective.id):
        raise APIError(401, "UNAUTHORIZED", "Session identity is invalid.")
    recipient = None
    if effective.role == "contractor":
        recipient = await db.scalar(select(Contractor.recipient_ref).where(Contractor.agency_id==session.agency_id, Contractor.user_id==effective.id))
        if recipient is None:
            raise APIError(401, "UNAUTHORIZED", "Contractor identity is unavailable.")
    return Actor(session.id, session.agency_id, principal.id, effective.id, effective.role, recipient, session.is_judge)


async def get_actor(request: Request, db: AsyncSession = Depends(get_db)):
    cookie = request.cookies.get(COOKIE)
    if not cookie or len(cookie) > 128:
        raise APIError(401, "UNAUTHORIZED", "Sign in to the workspace.")
    session = await db.scalar(select(SessionModel).where(SessionModel.cookie_hash==cookie_digest(cookie)))
    actor = await resolve_actor(db, session)
    request.state.session = session
    return actor


async def require_csrf(request: Request, actor: Actor = Depends(get_actor)):
    check_origin(request)
    supplied = request.headers.get("X-CSRF-Token", "")
    if len(supplied) > 128 or not hmac.compare_digest(supplied.encode(), csrf_token(request.state.session).encode()):
        raise APIError(403, "FORBIDDEN", "A valid session CSRF token is required.")
    return actor


async def require_owner(actor: Actor = Depends(get_actor)):
    if actor.role != "owner":
        raise APIError(403, "FORBIDDEN", "This action requires the agency owner persona.")
    return actor


async def require_judge(actor: Actor = Depends(get_actor)):
    if not actor.is_judge:
        raise APIError(403, "FORBIDDEN", "This action requires the original judge principal.")
    return actor


async def reauthorize(db, actor):
    session = await db.scalar(select(SessionModel).where(SessionModel.id==actor.session_id)
        .with_for_update(read=True).execution_options(populate_existing=True))
    current = await resolve_actor(db, session)
    if current != actor:
        raise APIError(401, "UNAUTHORIZED", "Session identity changed; sign in again.")


async def persona_user(db, agency_id, persona):
    if persona == "owner":
        user = await db.scalar(select(User).where(User.agency_id==agency_id, User.role=="owner"))
    else:
        user = await db.scalar(select(User).join(Contractor, (Contractor.agency_id==User.agency_id)&(Contractor.user_id==User.id)).where(User.agency_id==agency_id, User.role=="contractor", Contractor.recipient_ref==persona))
    if user is None:
        raise APIError(503, "DEPENDENCY_UNAVAILABLE", "The requested workspace persona is unavailable.")
    return user


def new_session(agency_id, principal_id, effective_id, is_judge, expires_at=None):
    cookie = secrets.token_urlsafe(32)
    session = SessionModel(id=uuid.uuid4(), agency_id=agency_id, principal_user_id=principal_id,
                           effective_user_id=effective_id, cookie_hash=cookie_digest(cookie),
                           csrf_nonce=secrets.token_urlsafe(32), is_judge=is_judge,
                           expires_at=expires_at or now()+timedelta(seconds=settings.SESSION_TTL_SECONDS))
    return session, cookie


def set_cookie(response, cookie):
    response.set_cookie(COOKIE, cookie, httponly=True, secure=settings.SESSION_COOKIE_SECURE,
                        samesite="lax", path="/", max_age=settings.SESSION_TTL_SECONDS)


def session_response(actor, session):
    return SessionResponse(principal_id=actor.principal_id, effective_user_id=actor.effective_user_id,
                           agency_id=actor.agency_id, role=actor.role, recipient_ref=actor.recipient_ref,
                           is_judge=actor.is_judge, csrf_token=csrf_token(session), expires_at=aware(session.expires_at))


def visible_tasks(actor):
    query = select(DeliveryTask).where(DeliveryTask.agency_id==actor.agency_id)
    if actor.role == "contractor":
        assignment = select(Mandate.id).join(MandateVersion, (MandateVersion.agency_id==Mandate.agency_id)&(MandateVersion.id==Mandate.current_version_id)).join(Contractor, (Contractor.agency_id==MandateVersion.agency_id)&(Contractor.id==MandateVersion.contractor_id)).where(Mandate.agency_id==actor.agency_id, Mandate.task_id==DeliveryTask.id, Contractor.user_id==actor.effective_user_id)
        query = query.where(exists(assignment.correlate(DeliveryTask)))
    return query


async def authorize_task(db, actor, task_id):
    task = await db.scalar(visible_tasks(actor).where(DeliveryTask.id==task_id))
    if task is None:
        raise APIError(404, "NOT_FOUND", "Task not found.")
    return task
