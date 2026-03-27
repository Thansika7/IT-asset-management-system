from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr

from app.server.schema import EmployeeRole

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
    phone: Optional[str]=None
    branch: Optional[str]=None
    role: EmployeeRole=EmployeeRole.EMPLOYEE

class EmployeeCreate(EmployeeBase):
    password: str

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
