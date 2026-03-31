from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class TrackingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    tracking_id: str
    asset_id: str
    asset_name: Optional[str] = None
    emp_id: str
    branch: Optional[str] = None
    from_branch: Optional[str] = None
    to_branch: Optional[str] = None
    movement_type: str
    movement_reason: Optional[str] = None
    assigned_date: datetime
    transfer_status: Optional[str] = None
    
    # Lifecycle Expiry Fields (fetched from AssetAttributeValue)
    license_expiry: Optional[str] = None
    warranty_expiry: Optional[str] = None
