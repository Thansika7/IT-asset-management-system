from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TrackingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    tracking_id: str
    asset_id: str
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None
    assigned_to: Optional[str] = None
    status: Optional[str] = None
    asset_name: Optional[str] = None
    emp_id: str
    employee_name: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    branch: Optional[str] = None
    from_branch: Optional[str] = None
    to_branch: Optional[str] = None
    movement_type: str
    movement_reason: Optional[str] = None
    allocation_type: str = "PERMANENT"
    returned_at: Optional[datetime] = None
    parent_tracking_id: Optional[str] = None
    assigned_date: datetime
    is_acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    transfer_status: Optional[str] = None
    
    # Lifecycle Expiry Fields (fetched from AssetAttributeValue)
    license_expiry: Optional[str] = None
    warranty_expiry: Optional[str] = None


class TrackingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TrackingRead]
    total: int
    page: int
    per_page: int


class TrackingOptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str


class TrackingFilterOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statuses: list[str]
    branches: list[TrackingOptionItem]
    employees: list[TrackingOptionItem]
    categories: list[str]

