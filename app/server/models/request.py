from pydantic import BaseModel
from typing import Optional

class RequestCreate(BaseModel):
    asset_name: str
    asset_category: str
    reason: str
    action_type: Optional[str] = "new"

class RequestTriage(BaseModel):
    action_type: str

class RequestReview(BaseModel):
    is_approved: bool

class RequestResponse(BaseModel):
    request_id: str
    emp_id: str
    asset_name: str
    asset_category: str
    reason: str
    action_type: str
    status: str
    stage: str
    
    class Config:
        from_attributes = True