import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class Request(Base):
    __tablename__="requests"
    request_id=Column(String(50), primary_key=True, index=True, default=lambda: f"REQ-{uuid.uuid4().hex[:8].upper()}")
    emp_id=Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    asset_name=Column(String(150), nullable=False)
    asset_category=Column(String(100), nullable=True)
    reason=Column(Text, nullable=True)
    hr_verified=Column(Boolean, nullable=True)
    status=Column(String(50), nullable=False, default="Pending")
    stage=Column(String(50), nullable=False, default="SUPPORT")
    action_type=Column(String(50), nullable=True)
    serviced_asset_id=Column(String(50), nullable=True)
    req_date=Column(DateTime(timezone=True), server_default=func.now())
    employee=relationship("Employee", back_populates="requests")
