import uuid
import enum
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class RequestType(str, enum.Enum):
    """Request types - REQUIRED field."""
    NEW = "NEW"                    # Request for new asset
    SERVICE = "SERVICE"            # Service/repair for existing asset
    REPLACE = "REPLACE"            # Replace existing asset
    RETURN = "RETURN"              # Return asset
    TRANSFER = "TRANSFER"          # Transfer asset between employees

class RequestStatus(str, enum.Enum):
    """Request lifecycle states - Enterprise workflow."""
    # Employee Stage
    SUBMITTED = "SUBMITTED"        # Employee creates request
    
    # HR Stage
    HR_VALIDATED = "HR_VALIDATED"  # HR approves request
    HR_REJECTED = "HR_REJECTED"    # HR rejects request
    
    # Triage Stage
    TRIAGED = "TRIAGED"            # Support has triaged (instance reserved)
    
    # Approval Stage
    APPROVED = "APPROVED"          # Manager has approved
    REJECTED = "REJECTED"          # Manager rejects (instance released)
    
    # Execution Stage
    ASSIGNED = "ASSIGNED"          # Asset assigned to user
    
    # Terminal States
    COMPLETED = "COMPLETED"        # Request fulfilled
    CANCELLED = "CANCELLED"        # User cancelled
    CLOSED = "CLOSED"              # Manager closed
    
    # Legacy (backward compat)
    PENDING = "PENDING"
    PENDING_SUPPORT = "PENDING_SUPPORT"
    PENDING_SUPPORT_TRIAGE = "PENDING_SUPPORT_TRIAGE"
    PENDING_MANAGER = "PENDING_MANAGER"
    APPROVED_FOR_SUPPORT = "APPROVED_FOR_SUPPORT"
    READY = "READY"
    WIP_SERVICE = "WIP_SERVICE"
    IN_REPAIR = "IN_REPAIR"
    AWAITING_TRANSFER = "AWAITING_TRANSFER"

class RequestPriority(str, enum.Enum):
    """Request priority levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class Request(Base):
    __tablename__="requests"
    __table_args__ = (
        CheckConstraint(
            "priority IS NULL OR priority IN ('CRITICAL','HIGH','MEDIUM','LOW')",
            name="ck_requests_priority_valid",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_requests_severity_valid",
        ),
        CheckConstraint(
            "urgency IS NULL OR urgency IN ('HIGH','MEDIUM','LOW')",
            name="ck_requests_urgency_valid",
        ),
        CheckConstraint(
            "status IN ('PENDING','TRIAGED','APPROVED','REJECTED','ASSIGNED','COMPLETED','CANCELLED','CLOSED')",
            name="ck_requests_status_valid",
        ),
        CheckConstraint(
            "request_type IN ('NEW','SERVICE','REPLACE','RETURN','TRANSFER')",
            name="ck_requests_type_valid",
        ),
    )
    request_id=Column(String(50), primary_key=True, index=True, default=lambda: f"REQ-{uuid.uuid4().hex[:8].upper()}")
    emp_id=Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True)
    
    # Request content
    asset_name=Column(String(150), nullable=False)
    asset_category=Column(String(100), nullable=True)
    reason=Column(Text, nullable=True)
    
    # Request type classification (REQUIRED)
    request_type=Column(Enum(RequestType, name="request_type"), nullable=False)  # NEW, SERVICE, REPLACE, RETURN, TRANSFER
    
    # Instance references
    instance_id=Column(String(50), ForeignKey("asset_instances.instance_id"), nullable=True)  # Current/requested instance
    serial_number=Column(String(100), nullable=True)
    
    # Legacy compatibility fields
    asset_id=Column(String(50), ForeignKey("assets.asset_id"), nullable=True)
    serviced_instance_id=Column(String(50), ForeignKey("asset_instances.instance_id"), nullable=True)
    serviced_asset_id=Column(String(50), nullable=True)
    action_type=Column(String(50), nullable=True)  # Legacy for tracking type
    
    # Lifecycle & status
    status=Column(Enum(RequestStatus, name="request_status"), nullable=False, default=RequestStatus.SUBMITTED)
    stage=Column(String(50), nullable=True)  # Legacy stage tracking
    
    # Approval & SLA tracking
    hr_verified=Column(Boolean, nullable=True)
    hr_validated_at=Column(DateTime(timezone=True), nullable=True)
    sla_priority=Column(String(20), nullable=True, default="MEDIUM")
    sla_due=Column(DateTime(timezone=True), nullable=True)
    sla_breached=Column(Boolean, nullable=False, default=False)
    priority=Column(String(20), nullable=True)
    severity=Column(String(20), nullable=True)
    urgency=Column(String(20), nullable=True)
    manager_notes=Column(Text, nullable=True)
    
    # Concurrency Control
    request_locked=Column(Boolean, nullable=False, default=False)
    locked_at=Column(DateTime(timezone=True), nullable=True)
    locked_by=Column(String(50), nullable=True)
    
    # Timestamps
    req_date=Column(DateTime(timezone=True), server_default=func.now())
    triaged_at=Column(DateTime(timezone=True), nullable=True)
    approved_at=Column(DateTime(timezone=True), nullable=True)
    rejected_at=Column(DateTime(timezone=True), nullable=True)
    assigned_at=Column(DateTime(timezone=True), nullable=True)
    completed_at=Column(DateTime(timezone=True), nullable=True)
    cancelled_at=Column(DateTime(timezone=True), nullable=True)
    closed_at=Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    employee=relationship("Employee", back_populates="requests")
    organization=relationship("Organization", back_populates="requests")
    requested_instance=relationship("AssetInstance", foreign_keys=[instance_id])
    serviced_instance=relationship("AssetInstance", foreign_keys=[serviced_instance_id])

    @property
    def requester_name(self) -> str | None:
        return self.employee.name if self.employee else None

    @property
    def requester_branch_name(self) -> str | None:
        return self.employee.branch_rel.branch_name if self.employee and self.employee.branch_rel else None

    @property
    def requester_role(self) -> str | None:
        return self.employee.role.value if self.employee and self.employee.role else None
