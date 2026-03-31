from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TrackingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    tracking_id: str
    asset_id: str
    asset_name: Optional[str] = None
    emp_id: str
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
