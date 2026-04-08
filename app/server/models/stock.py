from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from app.server.schema.asset import AssetStatus
from app.server.schema.tracking import MovementType, AllocationType
from datetime import date, datetime
from app.server.schema.employee import EmployeeRole

class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: Optional[str] = None
    name: str
    category_name: str
    sub_category_name: Optional[str] = None
    branch_id: Optional[str] = None
    branch: Optional[str] = None
    total_quantity: int = 1
    unused: int = 1
    purchase_cost: Optional[float] = 0.0
    salvage_value: Optional[float] = 0.0
    purchased_date: Optional[date] = None
    useful_life_years: int = 5

    @field_validator("asset_id")
    @classmethod
    def validate_optional_asset_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("asset_id must be a string")
        value = v.strip()
        return value or None

    @field_validator("name", "category_name")
    @classmethod
    def validate_text_fields(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("sub_category_name")
    @classmethod
    def validate_optional_subcategory(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("total_quantity")
    @classmethod
    def validate_total_quantity(cls, v: int) -> int:
        if v < 0:
            raise ValueError("total_quantity must be at least 0")
        return v

    @field_validator("unused")
    @classmethod
    def validate_unused(cls, v: int, info) -> int:
        if v < 0:
            raise ValueError("unused cannot be negative")
        total_quantity = info.data.get("total_quantity")
        if total_quantity is not None and v > total_quantity:
            raise ValueError("unused cannot be greater than total_quantity")
        return v

    @field_validator("purchase_cost", "salvage_value")
    @classmethod
    def validate_finance_values(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("financial values cannot be negative")
        return v

    @field_validator("useful_life_years")
    @classmethod
    def validate_useful_life(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("useful_life_years must be greater than zero")
        return v

class StockAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    quantity: int
    cost: Optional[float] = None
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    invoice_number: Optional[str] = None

    @field_validator("asset_id", "vendor_name", "vendor_contact", "invoice_number")
    @classmethod
    def validate_optional_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be at least 1")
        return v

    @field_validator("cost")
    @classmethod
    def validate_cost(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("cost cannot be negative")
        return v

class StockResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    asset_id: str
    name: str
    branch_id: Optional[str] = None
    branch: Optional[str] = None
    total_quantity: int
    used: int
    unused: int
    asset_status: AssetStatus

class AllocateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    emp_id: str
    allocation_type: AllocationType=AllocationType.PERMANENT
    parent_tracking_id: Optional[str]=None
    movement_reason: Optional[str]=None

    @field_validator("asset_id", "emp_id", "parent_tracking_id", "movement_reason")
    @classmethod
    def validate_allocate_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

class ReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracking_id: str
    movement_reason: Optional[str]=None

    @field_validator("tracking_id", "movement_reason")
    @classmethod
    def validate_return_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

class OnboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emp_id: str
    asset_ids: List[str]

    @field_validator("emp_id")
    @classmethod
    def validate_emp_id(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("emp_id must be a string")
        value = v.strip()
        if not value:
            raise ValueError("emp_id must not be blank")
        return value

    @field_validator("asset_ids")
    @classmethod
    def validate_asset_ids(cls, values: List[str]) -> List[str]:
        if not values:
            raise ValueError("asset_ids must contain at least one asset id")
        cleaned: List[str] = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Each asset id must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError("Asset ids must not be blank")
            if normalized in seen:
                raise ValueError("Asset ids must be unique")
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned


class OnboardingPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    target_role: Optional[EmployeeRole] = None
    branch: Optional[str] = None
    asset_ids: List[str]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("name must be a string")
        value = v.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("branch must be a string")
        value = v.strip()
        return value or None

    @field_validator("asset_ids")
    @classmethod
    def validate_asset_ids(cls, values: List[str]) -> List[str]:
        if not values:
            raise ValueError("asset_ids must contain at least one asset id")
        cleaned: List[str] = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Each asset id must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError("Asset ids must not be blank")
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned


class OnboardingPresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    preset_id: str
    name: str
    target_role: Optional[EmployeeRole] = None
    branch: Optional[str] = None
    asset_ids: List[str]
    created_at: datetime
