from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class OrganizationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_name: str
    domain: Optional[str] = None

class OrganizationCreate(OrganizationBase):
    pass

class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_name: Optional[str] = None
    domain: Optional[str] = None
    subscription_status: Optional[str] = None

class OrganizationResponse(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)
    organization_id: str
    subscription_status: str
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
