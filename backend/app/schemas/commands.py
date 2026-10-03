from datetime import datetime, timezone
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PositiveMoney(StrictModel):
    currency: Literal["USD"]
    value: str = Field(max_length=16, pattern=r"^(0|[1-9][0-9]{0,8})\.[0-9]{2}$")

    @field_validator("value")
    @classmethod
    def positive_value(cls, value):
        if value == "0.00":
            raise ValueError("Amount must be positive")
        return value

    @property
    def cents(self):
        return int(Decimal(self.value) * 100)


class PaymentTerms(StrictModel):
    recipient_ref: Literal["contractor_maya", "contractor_leo"]
    amount: PositiveMoney
    principal_cap: PositiveMoney
    max_attempts: int = Field(ge=1, le=3, strict=True)
    expires_at: datetime

    @field_validator("expires_at", mode="before")
    @classmethod
    def expiry_format(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Expiry requires an ISO timestamp")
        return value

    @field_validator("expires_at")
    @classmethod
    def utc_expiry(cls, value):
        if value.tzinfo is None:
            raise ValueError("Expiry requires an explicit timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def cap_covers_amount(self):
        if self.principal_cap.cents < self.amount.cents:
            raise ValueError("Principal cap must cover the amount")
        return self


class BriefCreate(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=4000)
    family: Literal["responsive_css", "api_endpoint", "keyboard_accessibility"]
    fixture_ref: Literal["checkout_fixture"]
    terms: PaymentTerms


class DeliveryCreate(StrictModel):
    artifact_version_id: uuid.UUID
    mandate_version_id: uuid.UUID
    expected_task_version: int = Field(ge=1, strict=True)
    claim: str = Field(min_length=1, max_length=4000)
