from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models import User, Contractor
from backend.app.schemas.api_schemas import SessionUser, SwitchRoleRequest
from backend.app.config import settings

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])

@router.get("/me", response_model=SessionUser)
async def get_current_session(db: AsyncSession = Depends(get_db)):
    # Defaults to owner persona
    stmt = select(User).where(User.agency_id == settings.DEFAULT_AGENCY_ID, User.role == "owner")
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        return SessionUser(
            user_id=settings.DEFAULT_AGENCY_ID,
            agency_id=settings.DEFAULT_AGENCY_ID,
            role="owner",
            display_name="Agency Owner (Demo)"
        )
    return SessionUser(
        user_id=user.id,
        agency_id=user.agency_id,
        role=user.role,
        display_name=user.display_name
    )

@router.post("/switch-role", response_model=SessionUser)
async def switch_role(req: SwitchRoleRequest, db: AsyncSession = Depends(get_db)):
    if req.target_role == "owner":
        stmt = select(User).where(User.agency_id == settings.DEFAULT_AGENCY_ID, User.role == "owner")
    elif req.target_role == "judge":
        stmt = select(User).where(User.agency_id == settings.DEFAULT_AGENCY_ID, User.role == "judge")
    elif req.target_role == "contractor":
        ref = req.contractor_ref or "contractor_maya"
        stmt = select(User).join(Contractor, Contractor.user_id == User.id).where(
            Contractor.agency_id == settings.DEFAULT_AGENCY_ID,
            Contractor.recipient_ref == ref
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid target role")

    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        # Fallback simulation
        name = "Contractor Maya" if req.contractor_ref == "contractor_maya" else f"{req.target_role.capitalize()} Demo"
        return SessionUser(
            user_id=settings.DEFAULT_AGENCY_ID,
            agency_id=settings.DEFAULT_AGENCY_ID,
            role=req.target_role,
            display_name=name
        )

    return SessionUser(
        user_id=user.id,
        agency_id=user.agency_id,
        role=user.role,
        display_name=user.display_name
    )
