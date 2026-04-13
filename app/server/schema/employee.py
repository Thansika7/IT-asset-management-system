import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class EmployeeRole(str, enum.Enum):
    SUPER_ADMIN="super_admin"  # Renamed from ADMIN
    ORG_ADMIN="org_admin"
    MANAGER="manager"
    HR="hr"
    SUPPORT_TEAM="support_team"
    EMPLOYEE="employee"

class Employee(Base):
    __tablename__="employees"
    employee_id=Column(String(50), primary_key=True, index=True, default=lambda: f"EMP-{uuid.uuid4().hex[:8].upper()}")
    name=Column(String(150), nullable=False)
    role=Column(
        Enum(
            EmployeeRole,
            name="employee_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EmployeeRole.EMPLOYEE,
    )
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True)
    
    phone=Column(String(20), nullable=True)
    email=Column(String(255), unique=True, index=True, nullable=False)
    personal_email=Column(String(255), unique=True, index=True, nullable=True)
    password_hash=Column(String(255), nullable=True)
    oauth_provider=Column(String(50), nullable=True)
    oauth_subject=Column(String(255), unique=True, nullable=True)
    is_active=Column(Boolean, nullable=False, default=True)
    password_reset_required=Column(Boolean, nullable=False, default=False)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    last_login_at=Column(DateTime(timezone=True), nullable=True)
    requests=relationship("Request", back_populates="employee", cascade="all, delete-orphan")
    transfers=relationship("Tracking", back_populates="employee", cascade="all, delete-orphan")
    permissions=relationship("EmployeePermission", back_populates="employee", uselist=False, cascade="all, delete-orphan")

    organization=relationship("Organization", back_populates="employees")
    branch_rel=relationship("Branch", back_populates="employees")

    @property
    def branch(self) -> str | None:
        return self.branch_rel.branch_name if self.branch_rel else None

class EmployeePermission(Base):
    __tablename__="employee_permissions"
    id=Column(Integer, primary_key=True, index=True)
    employee_id=Column(String(50), ForeignKey("employees.employee_id", ondelete="CASCADE"), unique=True, nullable=False)

    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=False, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)

    permissions_json=Column(JSON, nullable=False, default=dict)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    updated_at=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    employee=relationship("Employee", back_populates="permissions")

