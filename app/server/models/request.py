from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Request type constants
VALID_REQUEST_TYPES = {"NEW", "SERVICE", "REPLACE", "RETURN", "TRANSFER"}
REQUEST_TYPES_REQUIRING_INSTANCE = {"SERVICE", "REPLACE"}  # These MUST have instance_id
REQUEST_TYPES_OPTIONAL_INSTANCE = {"NEW", "RETURN"}        # These MAY have instance_id
REQUEST_TYPES_NO_INSTANCE = {}                              # None (but TRANSFER needs tracking)

class RequestType(str, Enum):
    """Request type enumeration."""
    NEW = "NEW"
    SERVICE = "SERVICE"
    REPLACE = "REPLACE"
    RETURN = "RETURN"
    TRANSFER = "TRANSFER"

class RequestStatus(str, Enum):
    """Request lifecycle status enumeration."""
    # Enterprise workflow
    SUBMITTED = "SUBMITTED"
    HR_VALIDATED = "HR_VALIDATED"
    HR_REJECTED = "HR_REJECTED"
    TRIAGED = "TRIAGED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    
    # Legacy (backward compat)
    PENDING = "PENDING"
    PENDING_SUPPORT = "PENDING_SUPPORT"
    PENDING_SUPPORT_TRIAGE = "PENDING_SUPPORT_TRIAGE"
    PENDING_MANAGER = "PENDING_MANAGER"
    APPROVED_FOR_SUPPORT = "APPROVED_FOR_SUPPORT"
    READY = "READY"
    WIP_SERVICE = "WIP_SERVICE"
    IN_REPAIR = "IN_REPAIR"
    AWAITING_TRANSFER = "AWAITING_TRANSFER"

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
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

# Legacy P-level priorities
class PriorityLevelLegacy(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

class RequestCreate(BaseModel):
    """
    Create a new request.
    
    request_type is REQUIRED and determines validation:
    - SERVICE: instance_id REQUIRED
    - REPLACE: instance_id REQUIRED
    - NEW: instance_id OPTIONAL
    - RETURN: instance_id OPTIONAL
    - TRANSFER: instance_id REQUIRED (must have tracking)
    """
    model_config = ConfigDict(extra="forbid")
    
    # Required fields
    asset_name: str
    asset_category: str
    reason: str
    request_type: RequestType  # NEW, SERVICE, REPLACE, RETURN, TRANSFER
    
    # Optional fields
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None
    priority: Optional[PriorityLevel] = PriorityLevel.MEDIUM
    severity: Optional[SeverityLevel] = SeverityLevel.MEDIUM
    urgency: Optional[UrgencyLevel] = UrgencyLevel.MEDIUM

    @field_validator("asset_name", "asset_category", "reason")
    @classmethod
    def validate_required_text(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("instance_id", "serial_number")
    @classmethod
    def validate_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None
    
    @field_validator("request_type", mode='after')
    @classmethod
    def validate_and_check_instance_requirement(cls, request_type: RequestType, info) -> RequestType:
        """Validate request type and enforce instance_id requirement."""
        req_type = request_type.value.upper()
        
        # Check if instance_id is required for this type
        if req_type in REQUEST_TYPES_REQUIRING_INSTANCE:
            instance_id = info.data.get("instance_id")
            if not instance_id or not instance_id.strip():
                raise ValueError(
                    f"request_type {req_type} REQUIRES instance_id. "
                    f"Cannot process {req_type} without specifying which asset instance."
                )
        
        return request_type

class RequestTriage(BaseModel):
    """
    Triage a request (support team operation).
    
    This reserves an instance for the request but does NOT modify it.
    Instance state transitions in approval workflow.
    """
    model_config = ConfigDict(extra="forbid")
    
    # Required: decision on what to do
    request_type: RequestType
    
    # Classification
    priority: PriorityLevel = PriorityLevel.MEDIUM
    severity: SeverityLevel = SeverityLevel.MEDIUM
    
    # For SERVICE/REPLACE, may specify which instance to use
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None

    @field_validator("request_type", mode='after')
    @classmethod
    def validate_request_type(cls, v: RequestType) -> RequestType:
        req_type = v.value.upper()
        if req_type not in VALID_REQUEST_TYPES:
            raise ValueError(f"request_type must be one of: {', '.join(sorted(VALID_REQUEST_TYPES))}")
        return v
    
    @field_validator("instance_id", "serial_number")
    @classmethod
    def validate_optional_triage_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None


class RequestReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_approved: bool

class RequestCrossBranchTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_branch: str

    @field_validator("target_branch")
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

class RequestHRValidation(BaseModel):
    """HR validates request eligibility."""
    model_config = ConfigDict(extra="forbid")
    is_valid: bool
    notes: Optional[str] = None

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

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
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None
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
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None
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
    request_types: list[str] = Field(default_factory=lambda: ["ASSET"])
    priorities: list[str] = Field(default_factory=lambda: ["P1", "P2", "P3", "P4"])
    severities: list[str] = Field(default_factory=lambda: ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    urgencies: list[str] = Field(default_factory=lambda: ["LOW", "MEDIUM", "HIGH"])
    action_types: list[str] = Field(default_factory=lambda: ["NEW", "SERVICE", "REPLACE"])


class RequestNecessityRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str
    confidence: int = Field(ge=0, le=100)
    summary: str
    factors: List[str] = Field(default_factory=list)
    model_note: str = "Advisory only; HR/Admin make final decisions."


class RequestFilterOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statuses: list[str]
    request_types: list[str]
    priorities: list[str]
    severities: list[str]
    branches: list[dict]


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
