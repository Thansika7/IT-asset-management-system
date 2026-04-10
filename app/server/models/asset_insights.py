from datetime import date
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class AssetListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category_id: Optional[str] = None
    category: Optional[str] = None
    sub_category_id: Optional[str] = None
    sub_category: Optional[str] = None
    branch_id: Optional[str] = None
    branch: Optional[str] = None
    status: str
    total_quantity: int
    used: int
    unused: int
    low_stock: bool


class AssetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AssetListItem]
    total: int
    page: int
    per_page: int


class AssetDetailRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    name: str
    category: Optional[str] = None
    sub_category: Optional[str] = None
    brand: Optional[str] = None
    branch: Optional[str] = None
    status: str
    total_quantity: int
    used: int
    unused: int
    low_stock: bool
    low_stock_threshold: int
    purchased_date: Optional[date] = None
    purchase_cost: float
    buying_value: float
    salvage_value: float
    reselling_value: float
    maintenance_cost: float
    service_cost: float
    maintenance_service_value: float
    repair_cost: float
    sub_license_cost: float
    asset_age_days: int
    useful_life_years: int
    annual_depreciation: float
    accumulated_depreciation: float
    book_value: float
    total_cost_of_ownership: float
    health_score: int
    recommendation: str
    recommendation_reason: str
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    invoice_number: Optional[str] = None


class AssetFinanceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    asset_name: str
    branch: Optional[str] = None
    purchased_date: Optional[date] = None
    purchase_cost: float
    buying_value: float
    salvage_value: float
    reselling_value: float
    maintenance_cost: float
    service_cost: float
    maintenance_service_value: float
    repair_cost: float
    sub_license_cost: float
    asset_age_days: int
    useful_life_years: int
    annual_depreciation: float
    accumulated_depreciation: float
    book_value: float
    total_cost_of_ownership: float


class AssetFinanceMonitorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    asset_name: str
    category: Optional[str] = None
    sub_category: Optional[str] = None
    branch: Optional[str] = None
    status: str
    total_quantity: int
    used: int
    unused: int
    low_stock: bool
    purchased_date: Optional[date] = None
    purchase_cost: float
    buying_value: float
    salvage_value: float
    reselling_value: float
    maintenance_cost: float
    service_cost: float
    maintenance_service_value: float
    repair_cost: float
    sub_license_cost: float
    asset_age_days: int
    useful_life_years: int
    annual_depreciation: float
    accumulated_depreciation: float
    book_value: float
    total_cost_of_ownership: float
    health_score: int
    health_classification: str
    replacement_recommendation: str
    recommendation_reason: str


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
    items: list[AssetFinanceMonitorItem]
    page: int = 1
    per_page: int = 20
    total: int = 0


class FinanceSortOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str


class AssetFinanceOptionsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sort_options: list[FinanceSortOption]


class AssetHealthRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None
    asset_name: Optional[str] = None
    status: Optional[str] = None
    health_score: int
    classification: str
    asset_age_years: float
    usage_duration_days: int
    repair_count: int
    failure_count: int = 0
    performance_issues_count: int
    warranty_expired: bool
    age_penalty: int
    repair_penalty: int
    failure_penalty: int = 0
    performance_penalty: int
    warranty_penalty: int
    usage_penalty: int
    recommendation_hint: str


class AssetHealthReportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    instance_id: Optional[str] = None
    serial_number: Optional[str] = None
    asset_name: str
    category: Optional[str] = None
    sub_category: Optional[str] = None
    branch: Optional[str] = None
    status: str
    health_score: int
    classification: str
    recommendation: str
    recommendation_reason: str
    asset_age_years: float
    usage_duration_days: int
    repair_count: int
    failure_count: int = 0
    performance_issues_count: int
    warranty_expired: bool
    purchase_cost: float
    maintenance_cost: float
    repair_cost: float
    reselling_value: float
    failure_penalty: int = 0


class AssetHealthReportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_count: int
    healthy_assets: int
    good_assets: int
    warning_assets: int
    critical_assets: int
    replacement_candidates: int
    items: list[AssetHealthReportItem]
    total: int = 0
    page: int = 1
    per_page: int = 20


class HealthRangeOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class AssetHealthFilterOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branches: List[str]
    categories: List[str]
    health_ranges: List[HealthRangeOption]
    statuses: List[str]


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


class SearchSuggestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    asset_name: str
    category: Optional[str] = None
    sub_category: Optional[str] = None
    branch: Optional[str] = None
    score: float = 0.0


class SearchResultsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    total: int
    did_you_mean: list[str] = []
    items: list[SearchSuggestionItem]


class CategoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: str
    category_name: str
    description: Optional[str] = None


class SubCategoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub_category_id: str
    category_id: str
    sub_category_name: str
    description: Optional[str] = None
