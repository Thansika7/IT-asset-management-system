from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

class ProcurementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    cost: float
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    invoice_number: Optional[str] = None
    reason: Optional[str] = "FINANCIAL_ENTRY"

    @field_validator("asset_id", "vendor_name", "vendor_contact", "invoice_number", "reason")
    @classmethod
    def validate_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("cost")
    @classmethod
    def validate_cost(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("cost must be greater than zero")
        return float(v)

class MaintenanceLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    cost: float
    reason: Optional[str] = "REPAIR"

    @field_validator("asset_id", "reason")
    @classmethod
    def validate_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("cost")
    @classmethod
    def validate_cost(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("cost must be greater than zero")
        return float(v)

class FinancialSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_asset_value: float
    total_maintenance_overhead: float
    unused_asset_value: float
    asset_count: int
    stock_count: int
