import re
from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.server.schema.employee import EmployeeRole

class Token(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: str="bearer"

class TokenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sub: str
    role: EmployeeRole
    exp: int
    emp_id: Optional[str] = None
    branch: Optional[str] = None
    organization_id: Optional[str] = None

class EmployeeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: EmailStr
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    branch: Optional[str] = None
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
    role: EmployeeRole = EmployeeRole.EMPLOYEE

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("branch", mode="before")
    @classmethod
    def normalize_branch(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        s = v.strip()
        return s or None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if not isinstance(v, str):
            raise ValueError("Email must be a string")
        return v.strip().lower()

    @field_validator("personal_email", mode="before")
    @classmethod
    def normalize_personal_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("personal_email must be a string")
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not re.fullmatch(r"^\d{10}$", v):
                raise ValueError("Phone number must be exactly 10 digits")
        return v

def _validate_password_strength(v: str) -> str:
    v = v.strip()
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one number (0-9)")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
        raise ValueError("Password must contain at least one special character")
    return v


class EmployeeCreate(EmployeeBase):
    """Manual onboarding: set email (company) + password. Auto provisioning: set personal_email only (omit password)."""

    email: Optional[EmailStr] = None  # type: ignore[assignment]
    password: Optional[str] = None
    onboarding_asset_ids: List[str] = Field(default_factory=list)
    preset_id: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _validate_password_strength(v)

    @field_validator("onboarding_asset_ids")
    @classmethod
    def validate_onboarding_asset_ids(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Each onboarding asset id must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError("Onboarding asset ids must not be blank")
            if normalized in seen:
                raise ValueError("Onboarding asset ids must be unique")
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned

    @field_validator("preset_id", mode="before")
    @classmethod
    def normalize_preset_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return None

    @model_validator(mode="after")
    def manual_or_auto(self):
        if self.password:
            if not self.email:
                raise ValueError("Company email is required when a password is supplied (manual onboarding).")
        else:
            if not self.personal_email:
                raise ValueError("Provide personal_email for automatic provisioning, or supply password with company email.")
        return self


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[EmployeeRole] = None
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("name must be a string")
        value = v.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("personal_email", mode="before")
    @classmethod
    def normalize_personal_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("personal_email must be a string")
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not re.fullmatch(r"^\d{10}$", v):
                raise ValueError("Phone number must be exactly 10 digits")
        return v


class EmployeeFilterOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statuses: List[str]
    roles: List[str]
    organizations: List[dict] = Field(default_factory=list)
    branches: List[dict] = Field(default_factory=list)

class OAuthEmployeeCreate(EmployeeBase):
    oauth_provider: str
    oauth_subject: str

    @field_validator("oauth_provider", "oauth_subject")
    @classmethod
    def validate_oauth_fields(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("OAuth fields must be strings")
        value = v.strip()
        if not value:
            raise ValueError("OAuth fields must not be blank")
        return value

class EmployeeRead(EmployeeBase):
    model_config=ConfigDict(from_attributes=True)
    employee_id: str
    is_active: bool
    branch_id: Optional[str] = None
    organization_id: Optional[str] = None
    password_reset_required: bool = False
    created_at: datetime
    last_login_at: Optional[datetime] = None
    permissions: Optional["EmployeePermissionRead"] = None

class EmployeePermissionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permissions_json: Dict[str, Dict[str, bool]] = Field(default_factory=dict)
    organization_id: Optional[str] = None
    branch_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("permissions_json", mode="before")
    @classmethod
    def normalize_permissions_json(cls, v):
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        return {}

class EmployeePermissionUpdate(EmployeePermissionBase):
    model_config = ConfigDict(extra="ignore")

class EmployeePermissionRead(EmployeePermissionBase):
    model_config = ConfigDict(from_attributes=True)
    employee_id: str


class PermissionActionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str


class PermissionModuleDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str
    actions: List[PermissionActionDef]


class PermissionCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modules: List[PermissionModuleDef]


class EmployeeAssetItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracking_id: str
    instance_id: str
    serial_number: Optional[str] = None
    asset_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    branch: Optional[str] = None
    status: str
    assigned_date: Optional[datetime] = None
    category: Optional[str] = None
    is_acknowledged: bool = False


class EmployeeAssetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str
    items: List[EmployeeAssetItem]
    total: int
    page: int
    per_page: int


class EmployeeAssetHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracking_id: str
    instance_id: str
    serial_number: Optional[str] = None
    asset_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    branch: Optional[str] = None
    category: Optional[str] = None
    assigned_date: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    movement_type: Optional[str] = None
    previous_assignment: bool = False
    repair_history: bool = False
    replacement_history: bool = False


class EmployeeAssetHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str
    items: List[EmployeeAssetHistoryItem]
    total: int
    page: int
    per_page: int


class EmployeeAssetFilterOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statuses: List[str]
    branches: List[str]
    categories: List[str]


class EmployeeAssetOwnerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_id: str
    asset_id: str
    asset_name: str
    status: str
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    assigned_at: Optional[datetime] = None
    tracking_id: Optional[str] = None
    movement_type: Optional[str] = None
    is_assigned: bool = False


class EmployeeAssetBulkAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_ids: List[str]
    reason: Optional[str] = "BULK_ASSIGNMENT"
    allocation_type: Optional[str] = "PERMANENT"

    @field_validator("instance_ids")
    @classmethod
    def validate_instance_ids(cls, values: List[str]) -> List[str]:
        if not values:
            raise ValueError("instance_ids must contain at least one instance id")
        cleaned: List[str] = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Each instance id must be a string")
            normalized = value.strip()
            if not normalized:
                raise ValueError("Instance ids must not be blank")
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned


class EmployeeAssetBulkAssignResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instance_id: str
    asset_id: Optional[str] = None
    tracking_id: Optional[str] = None
    reason: Optional[str] = None


class EmployeeAssetBulkAssignResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str
    assigned_count: int
    failed_count: int
    assigned_items: List[EmployeeAssetBulkAssignResultItem]
    failed_items: List[EmployeeAssetBulkAssignResultItem]


class EmployeeAssetOwnershipAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: str
    total_assets: int
    unreturned_assets: int
    overdue_assets: int
    overdue_days_threshold: int
    assets_by_status: Dict[str, int]



class EmployeeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[EmployeeRead]
    total: int
    page: int
    per_page: int

EmployeeRead.model_rebuild()

class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str

    @field_validator("current_password")
    @classmethod
    def strip_current(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Must not be blank")
        return v.strip()

    @field_validator("new_password")
    @classmethod
    def strong_new(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Must not be blank")
        return _validate_password_strength(v.strip())


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Email must be a string")
        return v.strip().lower()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: EmailStr
    password: str

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Username must be a string")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_login_password(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Password must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Password must not be blank")
        return value
