from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi.responses import JSONResponse
from backend.app.database import get_db
from backend.migrate import HEAD_REVISION

router = APIRouter(tags=["Health"])

@router.get("/livez")
async def livez():
    return {"status": "ok", "service": "proofpay-api"}

@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        if db.bind.dialect.name == "postgresql":
            revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != HEAD_REVISION:
                return JSONResponse(status_code=503, content={"status": "unavailable", "database": "migration_required"})
        return {
            "status": "ready",
            "database": "connected",
            "workflow": "unavailable",
        }
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "disconnected"},
        )
