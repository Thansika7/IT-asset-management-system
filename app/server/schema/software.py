from sqlalchemy import Column, Date, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.server.database.database import Base

class SoftwareAsset(Base):
    __tablename__="software_assets"
    software_assets_id=Column(Integer, primary_key=True, index=True)
    asset_id=Column(Integer, ForeignKey("assets.asset_id"), nullable=False, unique=True)
    software_name=Column(String(150), nullable=False)
    version=Column(String(50), nullable=True)
    license_key=Column(String(255), nullable=True)
    license_type=Column(String(100), nullable=True)
    vendor=Column(String(100), nullable=True)
    license_expiry=Column(Date, nullable=True)
    purchase_date=Column(Date, nullable=True)
    assigned_to=Column(Integer, ForeignKey("employees.employee_id"), nullable=True)
    asset=relationship("Asset", back_populates="software_details")
    assigned_employee=relationship("Employee", back_populates="software_assignments")
