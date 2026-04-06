import re
from datetime import datetime
from typing import Optional, List

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

class EmployeeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: EmailStr
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    branch: Optional[str] = None
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
    password_reset_required: bool = False
    created_at: datetime
    last_login_at: Optional[datetime]=None

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
