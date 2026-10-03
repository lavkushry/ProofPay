import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.api_schemas import CheckProposal


class CompilationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    brief_id: uuid.UUID
    revision_id: uuid.UUID
    status: str
    proposal: CheckProposal | None = None
    created_at: datetime


class CompilationAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    compilation_id: uuid.UUID
    job_id: uuid.UUID
    brief_id: uuid.UUID
    revision_id: uuid.UUID
    revision: int
    digest: str
    status: str
