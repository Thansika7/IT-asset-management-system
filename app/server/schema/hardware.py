from sqlalchemy import Column, Date, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.server.database.database import Base

class HardwareAsset(Base):
    __tablename__="hardware_assets"
    hardware_assets_id=Column(String(50), primary_key=True, index=True)
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=False, unique=True)
    asset_type=Column(String(100), nullable=False)
    brand=Column(String(100), nullable=True)
    model=Column(String(100), nullable=True)
    serial_number=Column(String(150), unique=True, index=True, nullable=True)
    cpu=Column(String(100), nullable=True)
    ram=Column(String(50), nullable=True)
    storage=Column(String(50), nullable=True)
    purchase_date=Column(Date, nullable=True)
    warranty_expiry=Column(Date, nullable=True)
    asset=relationship("Asset", back_populates="hardware_details")
