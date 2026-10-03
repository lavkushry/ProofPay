"""Bounded runner wire protocol and canonical delivery/evidence projections."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.app.schemas.api_schemas import CheckItem
from backend.app.schemas.commands import StrictModel

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CheckID = Literal["C01", "C02", "C03"]


class RunnerClaim(StrictModel):
    worker_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")


class RunnerHeartbeat(StrictModel):
    lease_token: uuid.UUID


class RunnerJob(StrictModel):
    job_id: uuid.UUID
    lease_token: uuid.UUID
    lease_until: datetime
    task_id: uuid.UUID
    delivery_id: uuid.UUID
    mandate_version_id: uuid.UUID
    mandate_digest: Digest
    artifact_version_id: uuid.UUID
    artifact_digest: Digest
    fixture_url: str = Field(max_length=512)
    checks: list[CheckItem] = Field(min_length=3, max_length=3)


class RunnerArtifactUpload(StrictModel):
    check_id: CheckID
    media_type: Literal["image/png"]
    sha256: Digest
    data_base64: str = Field(max_length=699052)


class RunnerResultUpload(StrictModel):
    check_id: CheckID
    outcome: Literal["pass", "fail", "error"]
    observations: dict
    screenshot_indexes: list[Annotated[int, Field(strict=True, ge=0, le=2)]] = Field(max_length=3)
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def utc_stamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("Observation timestamp requires a timezone")
        return value.astimezone(timezone.utc)


class RunnerCompletion(StrictModel):
    lease_token: uuid.UUID
    artifact_digest: Digest
    mandate_digest: Digest
    results: list[RunnerResultUpload] = Field(min_length=3, max_length=3)
    screenshots: list[RunnerArtifactUpload] = Field(max_length=3)


class RunnerCompletionResult(StrictModel):
    bundle_id: uuid.UUID
    state: Literal["accepted", "stale", "deduplicated"]


class DeliveryResponse(StrictModel):
    id: uuid.UUID
    task_id: uuid.UUID
    mandate_version_id: uuid.UUID
    artifact_version_id: uuid.UUID
    artifact_digest: Digest
    claim: str
    claim_ref: str
    sequence: int
    previous_delivery_id: uuid.UUID | None
    is_current: bool
    verification_job_id: uuid.UUID
    created_at: datetime
