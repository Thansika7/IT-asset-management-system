import uuid
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class Asset(Base):
    __tablename__="assets"
    asset_id=Column(String(50), primary_key=True, index=True, default=lambda: f"AST-{uuid.uuid4().hex[:8].upper()}")
    name=Column(String(150), nullable=False, index=True)
    category_id=Column(String(50), ForeignKey("categories.category_id"), nullable=False)
    sub_category_id=Column(String(50), ForeignKey("sub_categories.sub_category_id"), nullable=True)
    brand=Column(String(100), nullable=True)
    branch=Column(String(100), nullable=True, index=True)
    purchased_date=Column(Date, nullable=True)
    total_quantity=Column(Integer, nullable=False, default=0)
    used=Column(Integer, nullable=False, default=0)
    unused=Column(Integer, nullable=False, default=0)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    
    category=relationship("Category", back_populates="assets")
    sub_category=relationship("SubCategory", back_populates="assets")
    tracking_records=relationship("Tracking", back_populates="asset")
    attribute_values=relationship("AssetAttributeValue", back_populates="asset", cascade="all, delete-orphan")
