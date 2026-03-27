from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class Tracking(Base):
    __tablename__="tracking"
    tracking_id=Column(Integer, primary_key=True, index=True)
    asset_id=Column(Integer, ForeignKey("assets.asset_id"), nullable=False)
    asset_name=Column(String(150), nullable=True)
    emp_id=Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    category=Column(String(100), nullable=True)
    sub_category=Column(String(100), nullable=True)
    from_branch=Column(String(100), nullable=True)
    to_branch=Column(String(100), nullable=True)
    assigned_date=Column(DateTime(timezone=True), server_default=func.now())
    transfer_status=Column(String(50), nullable=True)
    license_expiry=Column(Date, nullable=True)
    warranty_expiry=Column(Date, nullable=True)
    asset=relationship("Asset", back_populates="tracking_records")
    employee=relationship("Employee", back_populates="transfers")
