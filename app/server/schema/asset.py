from sqlalchemy import Column, Date, DateTime, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class Asset(Base):
    __tablename__="assets"
    asset_id=Column(String(50), primary_key=True, index=True)
    name=Column(String(150), nullable=False, index=True)
    category=Column(String(100), nullable=False, index=True)
    sub_category=Column(String(100), nullable=True)
    brand=Column(String(100), nullable=True)
    branch=Column(String(100), nullable=True, index=True)
    purchased_date=Column(Date, nullable=True)
    total_quantity=Column(Integer, nullable=False, default=0)
    used=Column(Integer, nullable=False, default=0)
    unused=Column(Integer, nullable=False, default=0)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    tracking_records=relationship("Tracking", back_populates="asset")
    hardware_details=relationship("HardwareAsset", back_populates="asset", uselist=False)
    software_details=relationship("SoftwareAsset", back_populates="asset", uselist=False)
    furniture_details=relationship("FurnitureAsset", back_populates="asset", uselist=False)
