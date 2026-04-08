from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

class OrganizationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_name: str
    domain: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    admin_name: str
    admin_work_email: EmailStr
    admin_personal_email: EmailStr
    subscription_status: Optional[str] = "ACTIVE"
    subscription_start_at: Optional[datetime] = None
    subscription_end_at: Optional[datetime] = None

    @model_validator(mode="after")
    def subscription_window(self):
        if self.subscription_start_at and self.subscription_end_at:
            if self.subscription_end_at < self.subscription_start_at:
                raise ValueError("subscription_end_at must be on or after subscription_start_at")
        return self

    @field_validator("admin_name", mode="before")
    @classmethod
    def normalize_admin_name(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("admin_name must be a string")
        value = v.strip()
        if not value:
            raise ValueError("admin_name must not be blank")
        return value

    @field_validator("admin_work_email", "admin_personal_email", mode="before")
    @classmethod
    def normalize_admin_emails(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Email must be a string")
        return v.strip().lower()

class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_name: Optional[str] = None
    domain: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_start_at: Optional[datetime] = None
    subscription_end_at: Optional[datetime] = None

    @model_validator(mode="after")
    def subscription_window(self):
        if self.subscription_start_at and self.subscription_end_at:
            if self.subscription_end_at < self.subscription_start_at:
                raise ValueError("subscription_end_at must be on or after subscription_start_at")
        return self

class OrganizationResponse(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)
    organization_id: str
    subscription_status: str
    subscription_start_at: Optional[datetime] = None
    subscription_end_at: Optional[datetime] = None
    created_at: datetime


class OrganizationOnboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str
    organization_name: str
    domain: Optional[str] = None
    subscription_status: str
    subscription_start_at: Optional[datetime] = None
    subscription_end_at: Optional[datetime] = None
    org_admin_employee_id: str
    org_admin_name: str
    org_admin_work_email: EmailStr
    org_admin_personal_email: EmailStr
    created_at: datetime

class BranchBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_name: str
    location: Optional[str] = None

class BranchCreate(BranchBase):
    pass

class BranchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_name: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None

class BranchResponse(BranchBase):
    model_config = ConfigDict(from_attributes=True)
    branch_id: str
    organization_id: str
    status: str
    created_at: datetime
