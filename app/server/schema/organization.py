import uuid
import enum
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    TRIAL = "TRIAL"

class Organization(Base):
    __tablename__ = "organizations"
    organization_id = Column(String(50), primary_key=True, index=True, default=lambda: f"ORG-{uuid.uuid4().hex[:8].upper()}")
    organization_name = Column(String(150), nullable=False)
    domain = Column(String(150), nullable=True, unique=True)
    subscription_status = Column(Enum(SubscriptionStatus, name="subscription_status"), nullable=False, default=SubscriptionStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    branches = relationship("Branch", back_populates="organization", cascade="all, delete-orphan")
    employees = relationship("Employee", back_populates="organization", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="organization", cascade="all, delete-orphan")
    requests = relationship("Request", back_populates="organization", cascade="all, delete-orphan")

class BranchStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class Branch(Base):
    __tablename__ = "branches"
    branch_id = Column(String(50), primary_key=True, index=True, default=lambda: f"BRN-{uuid.uuid4().hex[:8].upper()}")
    organization_id = Column(String(50), ForeignKey("organizations.organization_id", ondelete="CASCADE"), nullable=False)
    branch_name = Column(String(150), nullable=False)
    location = Column(String(255), nullable=True)
    status = Column(Enum(BranchStatus, name="branch_status"), nullable=False, default=BranchStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="branches")
    employees = relationship("Employee", back_populates="branch_rel")
    assets = relationship("Asset", back_populates="branch_rel")
