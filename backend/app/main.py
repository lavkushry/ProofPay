from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import engine, Base
from backend.app.dependencies import require_workflow
from backend.app.routers import (
    health, sessions, catalog, briefs, mandates, tasks,
    deliveries, evidence, receipts, judge
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(
    title="ProofPay API",
    version="0.1.0",
    description="ProofPay compiles the review queue between 'work submitted' and 'payment released' into executable acceptance checks — and pays only when evidence passes.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(catalog.router)
app.include_router(briefs.router, dependencies=[Depends(require_workflow)])
app.include_router(mandates.router, dependencies=[Depends(require_workflow)])
app.include_router(tasks.router)
app.include_router(deliveries.router, dependencies=[Depends(require_workflow)])
app.include_router(evidence.router)
app.include_router(receipts.router)
app.include_router(judge.router, dependencies=[Depends(require_workflow)])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
