from pydantic import BaseModel
from typing import Optional

class ProcurementUpdate(BaseModel):
    asset_id: str
    cost: float
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    invoice_number: Optional[str] = None
    reason: Optional[str] = "FINANCIAL_ENTRY"

class MaintenanceLog(BaseModel):
    asset_id: str
    cost: float
    reason: Optional[str] = "REPAIR"

class FinancialSummary(BaseModel):
    total_asset_value: float
    total_maintenance_overhead: float
    unused_asset_value: float
    asset_count: int
    stock_count: int
