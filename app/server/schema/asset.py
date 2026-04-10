import uuid
import enum
from sqlalchemy import CheckConstraint, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Float, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base
class AssetStatus(str, enum.Enum):
    ACTIVE="ACTIVE"
    INACTIVE="INACTIVE"
    DISPOSED="DISPOSED"
    NEW="NEW"
    AVAILABLE="AVAILABLE"
    RESERVED="RESERVED"
    ASSIGNED="ASSIGNED"
    USED="USED"
    IN_REPAIR="IN_REPAIR"
    NOT_USABLE="NOT_USABLE"
    RETIRED="RETIRED"
    WARRANTY="WARRANTY" # Keep for compatibility if needed
    LOST="LOST"
    DAMAGED="DAMAGED"

class Asset(Base):
    __tablename__="assets"
    __table_args__ = (
        CheckConstraint("total_quantity >= 0", name="ck_assets_total_quantity_non_negative"),
        CheckConstraint("used >= 0", name="ck_assets_used_non_negative"),
        CheckConstraint("unused >= 0", name="ck_assets_unused_non_negative"),
        CheckConstraint("purchase_cost IS NULL OR purchase_cost >= 0", name="ck_assets_purchase_cost_non_negative"),
        CheckConstraint("salvage_value IS NULL OR salvage_value >= 0", name="ck_assets_salvage_value_non_negative"),
        CheckConstraint("maintenance_total_cost >= 0", name="ck_assets_maintenance_non_negative"),
        CheckConstraint("sub_license_cost >= 0", name="ck_assets_sub_license_non_negative"),
        CheckConstraint("repair_total_cost >= 0", name="ck_assets_repair_non_negative"),
        CheckConstraint("repair_count >= 0", name="ck_assets_repair_count_non_negative"),
        CheckConstraint("performance_issues_count >= 0", name="ck_assets_perf_issue_non_negative"),
        CheckConstraint("useful_life_years > 0", name="ck_assets_useful_life_positive"),
    )
    asset_id=Column(String(50), primary_key=True, index=True, default=lambda: f"AST-{uuid.uuid4().hex[:8].upper()}")
    name=Column(String(150), nullable=False, index=True)
    category_id=Column(String(50), ForeignKey("categories.category_id"), nullable=False)
    asset_behavior=Column(String(50), nullable=True, index=True)
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True)
    sub_category_id=Column(String(50), ForeignKey("sub_categories.sub_category_id"), nullable=True)
    brand=Column(String(100), nullable=True)
    model=Column(String(100), nullable=True)
    
    purchased_date=Column(Date, nullable=True)
    purchase_cost=Column(Float, nullable=True)
    salvage_value=Column(Float, nullable=True)
    invoice_number=Column(String(100), nullable=True)
    vendor_name=Column(String(150), nullable=True)
    vendor_contact=Column(String(255), nullable=True)
    maintenance_total_cost=Column(Float, nullable=False, default=0.0)
    repair_total_cost=Column(Float, nullable=False, default=0.0)
    repair_count=Column(Integer, nullable=False, default=0)
    performance_issues_count=Column(Integer, nullable=False, default=0)
    sub_license_cost=Column(Float, nullable=False, default=0.0)
    useful_life_years=Column(Integer, nullable=False, default=5)
    low_stock_threshold=Column(Integer, nullable=False, default=10)
    total_quantity=Column(Integer, nullable=False, default=0)
    used=Column(Integer, nullable=False, default=0)
    unused=Column(Integer, nullable=False, default=0)
    asset_status=Column(Enum(AssetStatus, name="asset_status"), nullable=False, default=AssetStatus.ACTIVE)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    
    organization=relationship("Organization", back_populates="assets")
    branch_rel=relationship("Branch", back_populates="assets")
    category=relationship("Category", back_populates="assets")

    @property
    def branch(self) -> str | None:
        return self.branch_rel.branch_name if self.branch_rel else None
    
    sub_category=relationship("SubCategory", back_populates="assets")
    tracking_records=relationship("Tracking", back_populates="asset") # Still links to Model for generic tracking if needed
    attribute_values=relationship("AssetAttributeValue", back_populates="asset", cascade="all, delete-orphan")
    instances=relationship("AssetInstance", back_populates="model", cascade="all, delete-orphan")

class AssetInstance(Base):
    __tablename__="asset_instances"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)
    
    # Instance UID - UUID-based for concurrency safety
    instance_id=Column(String(50), primary_key=True, index=True, default=lambda: f"INS-{uuid.uuid4().hex[:12].upper()}")
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=False, index=True) # Link to Model
    
    serial_number=Column(String(100), unique=True, nullable=True, index=True)
    asset_tag=Column(String(100), unique=True, nullable=True, index=True)
    
    status=Column(Enum(AssetStatus, name="asset_instance_status"), nullable=False, default=AssetStatus.AVAILABLE, index=True)
    
    # Vendor info at instance level
    vendor_name=Column(String(150), nullable=True)
    vendor_contact=Column(String(255), nullable=True)
    invoice_number=Column(String(100), nullable=True)
    
    # Instance-specific purchase data
    purchase_date=Column(Date, nullable=True)
    purchase_cost=Column(Float, nullable=True)
    repair_cost_total=Column(Float, nullable=False, default=0.0)
    maintenance_cost_total=Column(Float, nullable=False, default=0.0)
    warranty_expiry=Column(Date, nullable=True)
    license_key=Column(String(255), unique=True, nullable=True, index=True)
    expiry_date=Column(Date, nullable=True, index=True)
    subscription_term=Column(String(100), nullable=True)
    instance_metadata=Column(JSON, nullable=True)
    
    condition_notes=Column(Text, nullable=True)
    
    # Lifecycle tracking timestamps
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    assigned_at=Column(DateTime(timezone=True), nullable=True, index=True)
    returned_at=Column(DateTime(timezone=True), nullable=True)
    repair_started_at=Column(DateTime(timezone=True), nullable=True)
    repair_completed_at=Column(DateTime(timezone=True), nullable=True)
    retired_at=Column(DateTime(timezone=True), nullable=True)
    updated_at=Column(DateTime(timezone=True), onupdate=func.now())
    
    model=relationship("Asset", back_populates="instances")
    branch_rel=relationship("Branch")
    assigned_to_id=Column(String(50), ForeignKey("employees.employee_id"), nullable=True, index=True)
    assigned_to=relationship("Employee") # Mapping Employee -> asset_instance
    
    tracking_records=relationship("Tracking", back_populates="instance")

    @property
    def branch_name(self) -> str | None:
        return self.model.branch_rel.branch_name if self.model and self.model.branch_rel else None

    @property
    def branch(self) -> str | None:
        if self.branch_rel:
            return self.branch_rel.branch_name
        return self.model.branch if self.model else None

