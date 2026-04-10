import uuid
import enum
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text, JSON
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

class LifecycleEvent(str, enum.Enum):
    """Lifecycle events tracked for asset instances."""
    CREATED="CREATED"
    ASSIGNED="ASSIGNED"
    RETURNED="RETURNED"
    TRANSFERRED="TRANSFERRED"
    REPAIR_STARTED="REPAIR_STARTED"
    REPAIR_COMPLETED="REPAIR_COMPLETED"
    DAMAGED="DAMAGED"
    RETIRED="RETIRED"
    REPLACED="REPLACED"
    RESERVED="RESERVED"
    ROLLBACK="ROLLBACK"
    ATTRIBUTE_UPDATED="ATTRIBUTE_UPDATED"
    HARDWARE_UPGRADED="HARDWARE_UPGRADED"
    LICENSE_EXTENDED="LICENSE_EXTENDED"
    CONFIG_CHANGED="CONFIG_CHANGED"

class Tracking(Base):
    __tablename__="tracking"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)
    tracking_id=Column(String(50), primary_key=True, index=True, default=lambda: f"TRK-{uuid.uuid4().hex[:8].upper()}")
    
    # Model Link (Backward compatibility)
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=False)
    
    # New Instance Link
    instance_id=Column(String(50), ForeignKey("asset_instances.instance_id"), nullable=True)
    
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
    is_acknowledged=Column(Boolean, nullable=False, default=False)
    acknowledged_at=Column(DateTime(timezone=True), nullable=True)
    transfer_status=Column(String(50), nullable=True)
    
    asset=relationship("Asset", back_populates="tracking_records")
    instance=relationship("AssetInstance", back_populates="tracking_records")
    employee=relationship("Employee", back_populates="transfers")

class AssetLifecycle(Base):
    """Tracks complete lifecycle history of asset instances."""
    __tablename__="asset_lifecycle"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    
    lifecycle_id=Column(String(50), primary_key=True, index=True, default=lambda: f"LCY-{uuid.uuid4().hex[:8].upper()}")
    
    # Link to instance and asset
    instance_id=Column(String(50), ForeignKey("asset_instances.instance_id"), nullable=False, index=True)
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=False, index=True)
    
    # Event details
    event_type=Column(Enum(LifecycleEvent, name="lifecycle_event"), nullable=False, index=True)
    old_status=Column(String(50), nullable=True)
    new_status=Column(String(50), nullable=True)
    
    # Who performed the event
    performed_by=Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    
    # Event context
    timestamp=Column(DateTime(timezone=True), server_default=func.now(), index=True)
    notes=Column(Text, nullable=True)
    event_metadata=Column("metadata", JSON, nullable=True)
    
    # Optional tracking reference
    tracking_id=Column(String(50), ForeignKey("tracking.tracking_id"), nullable=True)
    
    # Instance relationships
    instance=relationship("AssetInstance")
    asset=relationship("Asset")
    performed_by_user=relationship("Employee", foreign_keys=[performed_by])

