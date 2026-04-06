from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_REQUEST_ACTIONS = {"NEW", "REPLACE", "SERVICE"}


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class UrgencyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PriorityLevel(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_name: str
    asset_category: str
    reason: str
    action_type: Optional[str] = None
    priority: Optional[PriorityLevel] = None
    severity: Optional[SeverityLevel] = None
    urgency: Optional[UrgencyLevel] = None

    @field_validator("asset_name", "asset_category", "reason")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v: Optional[str]) -> str:
        value = (v or "NEW").strip().upper()
        if value not in VALID_REQUEST_ACTIONS:
            raise ValueError(f"action_type must be one of: {', '.join(sorted(VALID_REQUEST_ACTIONS))}")
        return value

class RequestTriage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: str
    severity: SeverityLevel = SeverityLevel.MEDIUM
    urgency: Optional[UrgencyLevel] = None
    affected_users: int = 1

    @field_validator("affected_users")
    @classmethod
    def validate_affected_users(cls, v: int) -> int:
        if v < 1:
            raise ValueError("affected_users must be at least 1")
        return v

    @field_validator("action_type")
    @classmethod
    def validate_triage_action_type(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("action_type must be a string")
        value = v.strip()
        if not value:
            raise ValueError("action_type must not be blank")

        base_action = value.split(":", 1)[0].strip().upper()
        if base_action not in VALID_REQUEST_ACTIONS:
            raise ValueError(f"action_type must start with one of: {', '.join(sorted(VALID_REQUEST_ACTIONS))}")

        if ":" in value:
            _, branch = value.split(":", 1)
            if not branch.strip():
                raise ValueError("Selected target branch must not be blank")
            return f"{base_action}:{branch.strip()}"
        return base_action

class RequestReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_approved: bool

class RequestCrossBranchTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_branch: str
    target_asset_brand: str
    target_asset_name: str

    @field_validator("target_branch", "target_asset_brand", "target_asset_name")
    @classmethod
    def validate_transfer_fields(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

class RequestHRVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_needed: bool

class RequestResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution_notes: str
    repair_cost: Optional[float] = 0.0
    # True if the original asset is non-repairable and should be retired
    is_disposable: bool = False

    @field_validator("resolution_notes")
    @classmethod
    def validate_resolution_notes(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("resolution_notes must be a string")
        value = v.strip()
        if not value:
            raise ValueError("resolution_notes must not be blank")
        return value

    @field_validator("repair_cost")
    @classmethod
    def validate_repair_cost(cls, v: Optional[float]) -> float:
        if v is None:
            return 0.0
        if v < 0:
            raise ValueError("repair_cost cannot be negative")
        return float(v)

class RequestManagerNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_notes: str

    @field_validator("manager_notes")
    @classmethod
    def validate_manager_notes(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("manager_notes must be a string")
        return v.strip()

class RequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    request_id: str
    emp_id: str
    requester_name: Optional[str] = None
    requester_branch: Optional[str] = None
    requester_role: Optional[str] = None
    request_type: str = "ASSET"
    resignation_status: Optional[str] = None
    asset_name: str
    asset_category: str
    reason: str
    status: str
    stage: Optional[str] = None
    hr_verified: Optional[bool] = None
    action_type: Optional[str] = None
    priority: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    urgency_response_time: Optional[str] = None
    sla_target_at: Optional[datetime] = None
    sla_breached: bool = False
    escalation_triggered: bool = False
    escalation_role: Optional[str] = None
    severity_description: Optional[str] = None
    priority_description: Optional[str] = None
    priority_response_time: Optional[str] = None
    req_date: datetime
    manager_notes: Optional[str] = None


class RequestListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int
    per_page: int
    total: int
    items: List[RequestResponse]


class RequestFormAssetOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: Optional[str] = None
    asset_name: str
    category: Optional[str] = None
    sub_category: Optional[str] = None
    branch: Optional[str] = None
    owned_by_requester: bool = False


class RequestFormOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categories: list[str]
    reasons_by_category: dict[str, list[str]]
    known_assets: list[RequestFormAssetOption]


class RequestNecessityRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str
    confidence: int = Field(ge=0, le=100)
    summary: str
    factors: List[str] = Field(default_factory=list)
    model_note: str = "Advisory only; HR/Admin make final decisions."


class AssetNecessityRecommendationInput(BaseModel):
    """Inventory/asset panel necessity recommendation input for HR/Admin."""

    model_config = ConfigDict(extra="forbid")
    requester_employee_id: str
    reason: str

    @field_validator("requester_employee_id", "reason")
    @classmethod
    def strip_required_text(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        s = v.strip()
        if not s:
            raise ValueError("Value must not be blank")
        return s


class AdminDirectAllocationCreate(BaseModel):
    """Admin direct asset allocation without going through request workflow."""

    model_config = ConfigDict(extra="forbid")
    asset_id: str
    employee_id: str
    allocation_type: str = "PERMANENT"  # PERMANENT or TEMPORARY
    reason: str = "Direct allocation by admin"

    @field_validator("asset_id", "employee_id", "reason")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("allocation_type")
    @classmethod
    def validate_allocation_type(cls, v: str) -> str:
        value = v.strip().upper()
        if value not in ["PERMANENT", "TEMPORARY"]:
            raise ValueError("allocation_type must be either PERMANENT or TEMPORARY")
        return value


class AdminDirectAllocationResponse(BaseModel):
    """Response for direct asset allocation."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")
    tracking_id: str
    asset_id: str
    employee_id: str
    allocation_type: str
    movement_reason: str
    assigned_date: datetime
