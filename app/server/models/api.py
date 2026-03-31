import re
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    phone: Optional[str] = None
    branch: Optional[str] = None
    role: EmployeeRole = EmployeeRole.EMPLOYEE

    @field_validator("name", "branch", mode="before")
    @classmethod
    def normalize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("Value must be a string")
        value = v.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Email must be a string")
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not re.fullmatch(r"^\d{10}$", v):
                raise ValueError("Phone number must be exactly 10 digits")
        return v

class EmployeeCreate(EmployeeBase):
    password: str
    onboarding_asset_ids: List[str] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
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
    created_at: datetime
    last_login_at: Optional[datetime]=None

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
