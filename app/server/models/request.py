from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import datetime

VALID_REQUEST_ACTIONS = {"NEW", "REPLACE", "SERVICE"}


class RequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_name: str
    asset_category: str
    reason: str
    action_type: Optional[str] = "new"

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

class RequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    request_id: str
    emp_id: str
    requester_name: Optional[str] = None
    requester_branch: Optional[str] = None
    requester_role: Optional[str] = None
    asset_name: str
    asset_category: str
    reason: str
    status: str
    stage: Optional[str] = None
    hr_verified: Optional[bool] = None
    action_type: Optional[str] = None
    req_date: datetime
