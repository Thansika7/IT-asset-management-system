import uuid
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class Category(Base):
    __tablename__="categories"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)
    category_id=Column(String(50), primary_key=True, index=True, default=lambda: f"CAT-{uuid.uuid4().hex[:8].upper()}")
    category_name=Column(String(100), nullable=False, unique=True)
    description=Column(Text, nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    sub_categories=relationship("SubCategory", back_populates="category", cascade="all, delete-orphan")
    assets=relationship("Asset", back_populates="category")

class SubCategory(Base):
    __tablename__="sub_categories"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)
    sub_category_id=Column(String(50), primary_key=True, index=True, default=lambda: f"SUBCAT-{uuid.uuid4().hex[:8].upper()}")
    category_id=Column(String(50), ForeignKey("categories.category_id"), nullable=False)
    sub_category_name=Column(String(100), nullable=False)
    description=Column(Text, nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    category=relationship("Category", back_populates="sub_categories")
    asset_attributes=relationship("AssetAttribute", back_populates="sub_category", cascade="all, delete-orphan")
    assets=relationship("Asset", back_populates="sub_category")
