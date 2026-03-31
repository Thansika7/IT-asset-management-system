from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from app.server.schema.asset import AssetStatus
from app.server.schema.tracking import MovementType, AllocationType
from datetime import datetime

class AssetCreate(BaseModel):
    asset_id: str
    name: str
    category_name: str
    branch: str = "Headquarters"
    total_quantity: int = 1
    unused: int = 1

class StockAdd(BaseModel):
    asset_id: str
    quantity: int
    cost: Optional[float] = None
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    invoice_number: Optional[str] = None

class StockResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    asset_id: str
    name: str
    total_quantity: int
    used: int
    unused: int
    asset_status: AssetStatus

class AllocateRequest(BaseModel):
    asset_id: str
    emp_id: str
    allocation_type: AllocationType=AllocationType.PERMANENT
    parent_tracking_id: Optional[str]=None
    movement_reason: Optional[str]=None

class ReturnRequest(BaseModel):
    tracking_id: str
    movement_reason: Optional[str]=None

class OnboardRequest(BaseModel):
    emp_id: str
    asset_ids: List[str]
