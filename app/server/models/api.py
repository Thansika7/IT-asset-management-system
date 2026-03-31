import re
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.server.schema.employee import EmployeeRole

class Token(BaseModel):
    access_token: str
    token_type: str="bearer"

class TokenPayload(BaseModel):
    sub: str
    role: EmployeeRole
    exp: int

class EmployeeBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    branch: Optional[str] = None
    role: EmployeeRole = EmployeeRole.EMPLOYEE

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.fullmatch(r"^\d{10}$", v):
                raise ValueError("Phone number must be exactly 10 digits")
        return v

class EmployeeCreate(EmployeeBase):
    password: str
    onboarding_asset_ids: Optional[List[str]] = []

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number (0-9)")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v

class OAuthEmployeeCreate(EmployeeBase):
    oauth_provider: str
    oauth_subject: str

class EmployeeRead(EmployeeBase):
    model_config=ConfigDict(from_attributes=True)
    employee_id: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]=None

class LoginRequest(BaseModel):
    username: EmailStr
    password: str
