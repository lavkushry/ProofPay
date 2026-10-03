import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.app.schemas.commands import PaymentTerms, StrictModel


class BriefResponse(StrictModel):
    id: uuid.UUID
    task_id: uuid.UUID
    revision_id: uuid.UUID
    revision: int = Field(ge=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(max_length=160)
    text: str = Field(max_length=4000)
    family: Literal["responsive_css", "api_endpoint", "keyboard_accessibility"]
    fixture_ref: Literal["checkout_fixture"]
    terms: PaymentTerms
    created_at: datetime
    updated_at: datetime


class BriefList(StrictModel):
    items: list[BriefResponse] = Field(max_length=100)
    next_cursor: str | None
