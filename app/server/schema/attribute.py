import uuid
from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.orm import relationship
from app.server.database.database import Base

class AssetAttribute(Base):
    __tablename__="asset_attributes"
    attribute_id=Column(String(50), primary_key=True, index=True, default=lambda: f"ATTR-{uuid.uuid4().hex[:8].upper()}")
    sub_category_id=Column(String(50), ForeignKey("sub_categories.sub_category_id"), nullable=False)
    attribute_name=Column(String(100), nullable=False)
    data_type=Column(String(50), nullable=False)
    is_required=Column(Boolean, default=False)
    sub_category=relationship("SubCategory", back_populates="asset_attributes")
    values=relationship("AssetAttributeValue", back_populates="attribute", cascade="all, delete-orphan")

class AssetAttributeValue(Base):
    __tablename__="asset_attribute_values"
    value_id=Column(String(50), primary_key=True, index=True, default=lambda: f"VAL-{uuid.uuid4().hex[:8].upper()}")
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=False)
    attribute_id=Column(String(50), ForeignKey("asset_attributes.attribute_id"), nullable=False)
    value=Column(String(255), nullable=True)
    asset=relationship("Asset", back_populates="attribute_values")
    attribute=relationship("AssetAttribute", back_populates="values")
