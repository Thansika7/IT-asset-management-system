from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AssetListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    name: str
    category: Optional[str] = None
    sub_category: Optional[str] = None
    branch: Optional[str] = None
    status: str
    total_quantity: int
    used: int
    unused: int
    low_stock: bool


class AssetFinanceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    asset_name: str
    branch: Optional[str] = None
    purchased_date: Optional[date] = None
    purchase_cost: float
    salvage_value: float
    maintenance_cost: float
    repair_cost: float
    sub_license_cost: float
    asset_age_days: int
    useful_life_years: int
    annual_depreciation: float
    accumulated_depreciation: float
    book_value: float
    total_cost_of_ownership: float


class AssetFinanceReportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: Optional[str] = None
    asset_count: int
    total_purchase_cost: float
    total_maintenance_cost: float
    total_repair_cost: float
    total_license_cost: float
    total_depreciation: float
    total_cost_of_ownership: float


class AssetHealthRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    health_score: int
    age_penalty: int
    repair_penalty: int
    performance_penalty: int
    warranty_penalty: int
    usage_penalty: int
    recommendation_hint: str


class AssetRecommendationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    recommendation: str
    reason: str


class UtilizationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: Optional[str] = None
    category: Optional[str] = None
    asset_count: int
    total_quantity: int
    used_quantity: int
    unused_quantity: int
    usage_rate: float
    suggestion: Optional[str] = None
