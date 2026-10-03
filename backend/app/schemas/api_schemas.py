import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class SessionUser(BaseModel):
    user_id: uuid.UUID
    agency_id: uuid.UUID
    role: str
    display_name: str

class SwitchRoleRequest(BaseModel):
    target_role: str = Field(description="'owner', 'contractor', 'judge'")
    contractor_ref: Optional[str] = Field(default=None, description="'contractor_maya' or 'contractor_leo'")

# Briefs & Compilations
class BriefCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    family: str = Field(description="'responsive_css', 'api_endpoint', or 'keyboard_accessibility'")
    contractor_ref: str = Field(description="'contractor_maya' or 'contractor_leo'")
    amount_usd: float = Field(gt=0, default=75.00)
    expires_in_hours: int = Field(default=24, ge=1)

class CheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_id: str = Field(description="'C01', 'C02', 'C03'")
    template_type: str
    params: Dict[str, Any]
    compiled_by: str = "ai"
    approved: bool = False

class CheckProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checks: List[CheckItem] = Field(default_factory=list)
    ambiguities: List[str] = Field(default_factory=list)
    clarifying_questions: List[str] = Field(default_factory=list)

class BriefResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    current_revision_id: Optional[uuid.UUID] = None
    title: str
    body: str
    family: str
    proposal: Optional[CheckProposal] = None

# Mandates
class MandateApprovalRequest(BaseModel):
    mandate_version_id: uuid.UUID
    expected_digest: str

class MandateResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    version: int
    lifecycle_state: str
    amount_cents: int
    currency: str = "USD"
    checks: List[CheckItem]
    payload_digest: str
    approved_at: Optional[datetime] = None

# Tasks & Queue
class DeliveryTaskResponse(BaseModel):
    id: uuid.UUID
    brief_id: uuid.UUID
    title: str
    state: str
    amount_usd: float
    contractor_name: str
    review_required: bool = False
    hold_reasons: List[str] = []
    current_delivery_id: Optional[uuid.UUID] = None
    updated_at: datetime

# Deliveries
class DeliverySubmitRequest(BaseModel):
    task_id: uuid.UUID
    artifact_ref: str = Field(description="'checkout_mobile_broken' or 'checkout_mobile_fixed'")
    claim: str = Field(min_length=1, max_length=4000)

class DeliveryResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    sequence: int
    artifact_ref: str
    claim: str
    created_at: datetime

# Evidence & AI Review
class CheckObservation(BaseModel):
    check_id: str
    outcome: str # 'pass', 'fail', 'error'
    observations: Dict[str, Any]

class EvidenceReviewResult(BaseModel):
    verdict: str # 'pass', 'fail', 'uncertain'
    per_check_results: List[CheckObservation]
    contradictions: List[str] = []
    rationale: str
    evidence_refs: List[str] = []

class EvidenceBundleResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    delivery_id: uuid.UUID
    bundle_digest: str
    results: List[CheckObservation]
    screenshot_artifact_id: Optional[uuid.UUID] = None
    ai_review: Optional[EvidenceReviewResult] = None

# Correction
class CorrectionResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    contractor_message: str
    evidence_refs: List[str]
    created_at: datetime

# Payments & Receipts
class ReceiptResponse(BaseModel):
    task_id: uuid.UUID
    brief_title: str
    contractor_ref: str
    amount_usd: float
    currency: str = "USD"
    item_status: str # 'success', 'processing', etc.
    provider_batch_id: Optional[str] = None
    provider_item_id: Optional[str] = None
    mandate_digest: str
    bundle_digest: str
    paid_at: Optional[datetime] = None

# Judge / Reset
class JudgeResetResponse(BaseModel):
    status: str
    active_demo_run_id: uuid.UUID
    message: str
