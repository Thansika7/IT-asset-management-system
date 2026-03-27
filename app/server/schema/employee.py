import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class EmployeeRole(str, enum.Enum):
    ADMIN="admin"
    MANAGER="manager"
    HR="hr"
    SUPPORT_TEAM="support_team"
    EMPLOYEE="employee"

class Employee(Base):
    __tablename__="employees"
    employee_id=Column(String(50), primary_key=True, index=True, default=lambda: f"EMP-{uuid.uuid4().hex[:8].upper()}")
    name=Column(String(150), nullable=False)
    role=Column(Enum(EmployeeRole, name="employee_role"), nullable=False, default=EmployeeRole.EMPLOYEE)
    phone=Column(String(20), nullable=True)
    email=Column(String(255), unique=True, index=True, nullable=False)
    branch=Column(String(100), nullable=True)
    password_hash=Column(String(255), nullable=True)
    oauth_provider=Column(String(50), nullable=True)
    oauth_subject=Column(String(255), unique=True, nullable=True)
    is_active=Column(Boolean, nullable=False, default=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    last_login_at=Column(DateTime(timezone=True), nullable=True)
    requests=relationship("Request", back_populates="employee")
    transfers=relationship("Tracking", back_populates="employee")

