import uuid
import enum
from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base
class MovementType(str, enum.Enum):
    ALLOCATE="ALLOCATE"
    RETURN="RETURN"
    TRANSFER="TRANSFER"
    REPAIR="REPAIR"
    WARRANTY="WARRANTY"
    REPLACE="REPLACE"
    ONBOARD="ONBOARD"
    OFFBOARD="OFFBOARD"
class AllocationType(str, enum.Enum):
    TEMPORARY="TEMPORARY"
    PERMANENT="PERMANENT"
class Tracking(Base):
    __tablename__="tracking"
    tracking_id=Column(String(50), primary_key=True, index=True, default=lambda: f"TRK-{uuid.uuid4().hex[:8].upper()}")
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=False)
    asset_name=Column(String(150), nullable=True)
    emp_id=Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    category=Column(String(100), nullable=True)
    sub_category=Column(String(100), nullable=True)
    branch=Column(String(100), nullable=True)
    from_branch=Column(String(100), nullable=True)
    to_branch=Column(String(100), nullable=True)
    movement_type=Column(Enum(MovementType, name="movement_type"), nullable=False, default=MovementType.ALLOCATE)
    movement_reason=Column(Text, nullable=True)
    allocation_type=Column(Enum(AllocationType, name="allocation_type"), nullable=False, default=AllocationType.PERMANENT)
    returned_at=Column(DateTime(timezone=True), nullable=True)
    parent_tracking_id=Column(String(50), nullable=True)
    assigned_date=Column(DateTime(timezone=True), server_default=func.now())
    transfer_status=Column(String(50), nullable=True)
    asset=relationship("Asset", back_populates="tracking_records")
    employee=relationship("Employee", back_populates="transfers")
