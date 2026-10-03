"""Canonical mandate commands and public, receiver-free version projections."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.app.schemas.api_schemas import CheckItem
from backend.app.schemas.commands import PaymentTerms, PositiveMoney, StrictModel


class MandateDraftCreate(StrictModel):
    task_id: uuid.UUID
    brief_revision_id: uuid.UUID
    compilation_id: uuid.UUID
    terms: PaymentTerms


class MandateVersionCreate(StrictModel):
    brief_revision_id: uuid.UUID
    compilation_id: uuid.UUID
    terms: PaymentTerms
    expected_current_version_id: uuid.UUID | None


class ApproveRequest(StrictModel):
    expected_draft_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_current_version_id: uuid.UUID | None


class Payer(StrictModel):
    account_ref: Literal["payer_sandbox_us"]


class Payee(StrictModel):
    recipient_ref: Literal["contractor_maya", "contractor_leo"]
    display_name: str = Field(max_length=120)
    email_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class Budget(StrictModel):
    max_total: str = Field(max_length=16, pattern=r"^(0|[1-9][0-9]{0,8})\.[0-9]{2}$")
    max_attempts: int = Field(ge=1, le=3)


class Authority(StrictModel):
    type: Literal["conditional_release"]
    condition: Literal["all checks pass"]
    expires_at: datetime


class ApprovalAudit(StrictModel):
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    immutable: bool


class MandatePayload(StrictModel):
    mandate_id: uuid.UUID
    version: int = Field(ge=1)
    status: Literal["draft", "approved"]
    payer: Payer
    payee: Payee
    amount: PositiveMoney
    budget: Budget
    authority: Authority
    acceptance_checks: list[CheckItem] = Field(min_length=3, max_length=3)
    audit: ApprovalAudit


class MandateVersionResponse(StrictModel):
    id: uuid.UUID
    mandate_id: uuid.UUID
    version: int = Field(ge=1)
    lifecycle_state: Literal["draft", "approved", "expired", "superseded", "exhausted"]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: MandatePayload
    created_at: datetime


class MandateResponse(StrictModel):
    id: uuid.UUID
    task_id: uuid.UUID
    current_version_id: uuid.UUID | None
    versions: list[MandateVersionResponse] = Field(max_length=50)
