from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SoftwareAssignPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    employee_id: str
    software_asset_id: str
    instance_id: str
    notes: Optional[str] = None

    @field_validator("request_id", "employee_id", "software_asset_id", "instance_id")
    @classmethod
    def validate_required_ids(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Value must not be blank")
        return text

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class SoftwareRemovePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    reason: str
    create_service_request: bool = False
    service_reason: Optional[str] = None

    @field_validator("assignment_id", "reason")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Value must not be blank")
        return text

    @field_validator("service_reason")
    @classmethod
    def normalize_service_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class SoftwareHardwareOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    asset_id: str
    asset_name: str
    sub_category: Optional[str] = None
    status: str
    assigned_to_id: Optional[str] = None


class SoftwareAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    request_id: str
    employee_id: str
    software_asset_id: str
    instance_id: str
    request_status: str
    assigned_at: Optional[datetime] = None


class SoftwareRemovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    removal_tracking_id: str
    software_asset_id: str
    instance_id: str
    employee_id: str
    removed_at: Optional[datetime] = None
    followup_request_id: Optional[str] = None


class SoftwareAssignmentHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_id: str
    assignment_id: Optional[str] = None
    movement_type: str
    software_asset_id: str
    software_name: Optional[str] = None
    instance_id: Optional[str] = None
    employee_id: str
    employee_name: Optional[str] = None
    notes: Optional[str] = None
    assigned_date: Optional[datetime] = None
    returned_at: Optional[datetime] = None


class SoftwareUsageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    software_asset_id: str
    software_name: str
    total: int = Field(ge=0)
    assigned: int = Field(ge=0)
    available: int = Field(ge=0)
