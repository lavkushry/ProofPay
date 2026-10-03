from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import engine
from backend.app.dependencies import require_workflow
from backend.app.errors import install_errors
from backend.app.services.auth import get_actor
from backend.app.routers import (
    health, sessions, catalog, briefs, mandates, tasks,
    catalog_canonical, deliveries, evidence, receipts, judge, brief_commands, jobs, delivery_commands
)

@asynccontextmanager
async def lifespan(app: FastAPI):
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
install_errors(app)

# Register routers
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(catalog.router, dependencies=[Depends(get_actor)])
app.include_router(catalog_canonical.router, dependencies=[Depends(get_actor)])
app.include_router(brief_commands.router)
app.include_router(delivery_commands.router)
app.include_router(jobs.router)
app.include_router(briefs.router, dependencies=[Depends(get_actor)])
app.include_router(mandates.router, dependencies=[Depends(get_actor)])
app.include_router(tasks.router)
app.include_router(deliveries.router)
app.include_router(evidence.router)
app.include_router(receipts.router)
app.include_router(judge.router, dependencies=[Depends(require_workflow)])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
