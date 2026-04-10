from pydantic import BaseModel, ConfigDict, field_validator, Field, model_validator
from typing import Optional, List
from app.server.schema.asset import AssetStatus
from app.server.schema.tracking import MovementType, AllocationType, LifecycleEvent
from datetime import date, datetime
from app.server.schema.employee import EmployeeRole


class AssetSpecificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute_id: Optional[str] = None
    attribute_name: Optional[str] = None
    value: str
    data_type: str = "text"
    is_required: bool = False

    @field_validator("attribute_name")
    @classmethod
    def validate_attribute_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Attribute value must not be blank")
        return value

class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: Optional[str] = None
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    asset_behavior: Optional[str] = None
    sub_category_id: Optional[str] = None
    sub_category_name: Optional[str] = None
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
    purchased_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    salvage_value: Optional[float] = None
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    invoice_number: Optional[str] = None
    warranty_expiry: Optional[date] = None
    expiry_date: Optional[date] = None
    subscription_term: Optional[str] = None
    instance_metadata: Optional[dict] = None
    total_quantity: int = 0
    unused: int = 0
    useful_life_years: int = 5
    specifications: List[AssetSpecificationInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_text_fields(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("brand", "model")
    @classmethod
    def validate_optional_model_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("category_name", "sub_category_name", "vendor_name", "vendor_contact", "invoice_number", "asset_behavior", "subscription_term")
    @classmethod
    def validate_optional_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("asset_behavior")
    @classmethod
    def validate_asset_behavior(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        allowed = {"instance_based", "quantity_based", "subscription_based", "license_based"}
        if v not in allowed:
            raise ValueError(f"asset_behavior must be one of {sorted(allowed)}")
        return v

    @field_validator("useful_life_years")
    @classmethod
    def validate_useful_life(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("useful_life_years must be positive")
        return v

    @field_validator("total_quantity", "unused")
    @classmethod
    def validate_quantities(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Quantity fields cannot be negative")
        return v

    @model_validator(mode="after")
    def validate_create_payload(self):
        if not (self.category_id or self.category_name):
            raise ValueError("Either category_id or category_name is required")
        if not (self.sub_category_id or self.sub_category_name):
            raise ValueError("Either sub_category_id or sub_category_name is required")
        if self.total_quantity <= 0:
            raise ValueError("total_quantity must be greater than zero")
        if self.unused == 0:
            self.unused = self.total_quantity
        return self

class AssetInstanceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str  # Link to Model
    serial_number: Optional[str] = None
    asset_tag: Optional[str] = None
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = 0.0
    warranty_expiry: Optional[date] = None
    branch_id: Optional[str] = None
    condition_notes: Optional[str] = None

class StockAdd(BaseModel):
    """Adding stock now means creating instances or incrementing generic count."""
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    instances: List[AssetInstanceCreate] = Field(default_factory=list)
    quantity: int = 0  # If adding generic items without instances
    cost: Optional[float] = None
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None


class AssetAttributeUpdateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute_id: Optional[str] = None
    attribute_name: Optional[str] = None
    new_value: Optional[str] = None

    @field_validator("attribute_id", "attribute_name")
    @classmethod
    def validate_optional_identifier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @field_validator("new_value")
    @classmethod
    def normalize_new_value(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @model_validator(mode="after")
    def validate_attribute_target(self):
        if not self.attribute_id and not self.attribute_name:
            raise ValueError("Either attribute_id or attribute_name is required")
        return self


class AssetAttributeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: List[AssetAttributeUpdateItem] = Field(default_factory=list)
    event_type: LifecycleEvent = LifecycleEvent.ATTRIBUTE_UPDATED
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip()
        return value or None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.changes:
            raise ValueError("At least one attribute change is required")
        return self


class AssetAttributeUpdateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute_id: str
    attribute_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    value_id: str
    lifecycle_id: str
    event_type: str


class AssetAttributeUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_id: str
    asset_id: str
    event_type: str
    reason: Optional[str] = None
    updated_count: int
    updates: List[AssetAttributeUpdateResult]

class AssetInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    instance_id: str
    asset_id: str
    branch: Optional[str] = None
    serial_number: Optional[str] = None
    asset_tag: Optional[str] = None
    status: AssetStatus
    assigned_to_id: Optional[str] = None
    purchase_date: Optional[date] = None
    warranty_expiry: Optional[date] = None
    license_key: Optional[str] = None
    expiry_date: Optional[date] = None
    subscription_term: Optional[str] = None
    instance_metadata: Optional[dict] = None

class InventorySnapshot(BaseModel):
    """
    Inventory counts calculated from AssetInstance statuses.
    This is the single source of truth for inventory.
    Static counters (used, unused, total_quantity) are legacy only.
    """
    model_config = ConfigDict(extra="forbid")
    total: int = 0
    available: int = 0
    assigned: int = 0
    in_repair: int = 0
    not_usable: int = 0
    retired: int = 0
    allocatable: int = 0  # Alias for available that can be allocated
    
    @classmethod
    def from_service(cls, service_snapshot):
        """Convert service InventorySnapshot to Pydantic model."""
        return cls(
            total=service_snapshot.total,
            available=service_snapshot.available,
            assigned=service_snapshot.assigned,
            in_repair=service_snapshot.in_repair,
            not_usable=service_snapshot.not_usable,
            retired=service_snapshot.retired,
            allocatable=service_snapshot.allocatable()
        )

class StockResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    asset_id: str
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    # Legacy fields (for backward compatibility, but not always accurate)
    total_quantity: int
    used: int
    unused: int
    # New dynamic inventory (source of truth)
    inventory: Optional[InventorySnapshot] = None
    instances: List[AssetInstanceRead] = Field(default_factory=list)
class StockListResponse(BaseModel):
    items: List[StockResponse]
    total: int
    page: int
    per_page: int

class AssetInstanceListResponse(BaseModel):
    items: List[AssetInstanceRead]
    total: int
    page: int
    per_page: int


class AssetInstanceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_id: str
    asset_id: str
    asset_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    branch_id: Optional[str] = None
    branch: Optional[str] = None
    status: str
    assigned_to_id: Optional[str] = None
    assigned_to: Optional[str] = None
    category_id: Optional[str] = None
    category: Optional[str] = None


class AssetInstancePagedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[AssetInstanceListItem]
    total: int
    page: int
    per_page: int


class FilterOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str
    id: Optional[str] = None
    name: Optional[str] = None

    @model_validator(mode="after")
    def set_standardized_fields(self):
        if not self.id:
            self.id = self.value
        if not self.name:
            self.name = self.label
        return self


class AssetInstanceFilterOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statuses: List[str]
    branches: List[FilterOption]
    categories: List[FilterOption]
    assignees: List[FilterOption]

class AllocateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str # Model ID
    instance_id: Optional[str] = None # Specific Physical Item
    emp_id: str
    allocation_type: AllocationType=AllocationType.PERMANENT
    movement_reason: Optional[str]=None

class ReturnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracking_id: str
    movement_reason: Optional[str]=None

class OnboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    emp_id: str
    instance_ids: List[str]

class OnboardingPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    target_role: Optional[EmployeeRole] = None
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
    asset_model_ids: List[str]

class OnboardingPresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    preset_id: str
    name: str
    target_role: Optional[EmployeeRole] = None
    asset_ids: List[str]
    created_at: datetime


class OnboardingPresetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[OnboardingPresetRead]
    total: int
    page: int
    per_page: int
