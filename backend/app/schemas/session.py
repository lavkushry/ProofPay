import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Persona = Literal["owner", "contractor_maya", "contractor_leo"]


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_code: str = Field(min_length=1, max_length=256)
    persona: Persona


class RoleSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona: Persona


class SessionResponse(BaseModel):
    principal_id: uuid.UUID
    effective_user_id: uuid.UUID
    agency_id: uuid.UUID
    role: Literal["owner", "contractor"]
    recipient_ref: Literal["contractor_maya", "contractor_leo"] | None
    is_judge: bool
    csrf_token: str
    expires_at: datetime
