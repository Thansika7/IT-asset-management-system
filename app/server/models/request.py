from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RequestCreate(BaseModel):
    asset_name: str
    asset_category: str
    reason: str

class RequestTriage(BaseModel):
    action_type: str

class RequestReview(BaseModel):
    is_approved: bool

class RequestResolve(BaseModel):
    resolution_notes: str
    repair_cost: Optional[float] = 0.0
    # True if the original asset is non-repairable and should be retired
    is_disposable: bool = False

class RequestResponse(BaseModel):
    request_id: str
    emp_id: str
    asset_name: str
    asset_category: str
    reason: str
    status: str
    stage: Optional[str] = None
    action_type: Optional[str] = None
    req_date: datetime

    class Config:
        from_attributes = True
