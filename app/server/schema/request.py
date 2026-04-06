import uuid
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.server.database.database import Base

class Request(Base):
    __tablename__="requests"
    __table_args__ = (
        CheckConstraint(
            "priority IS NULL OR priority IN ('P1','P2','P3','P4')",
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
    )
    request_id=Column(String(50), primary_key=True, index=True, default=lambda: f"REQ-{uuid.uuid4().hex[:8].upper()}")
    emp_id=Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    asset_name=Column(String(150), nullable=False)
    asset_category=Column(String(100), nullable=True)
    reason=Column(Text, nullable=True)
    hr_verified=Column(Boolean, nullable=True)
    status=Column(String(50), nullable=False, default="Pending")
    stage=Column(String(50), nullable=False, default="SUPPORT")
    action_type=Column(String(50), nullable=True)
    priority=Column(String(20), nullable=True, default="P3")
    severity=Column(String(20), nullable=True, default="MEDIUM")
    urgency=Column(String(20), nullable=True, default="MEDIUM")
    serviced_asset_id=Column(String(50), nullable=True)
    request_type=Column(String(20), nullable=False, default="ASSET")
    resignation_status=Column(String(20), nullable=True)
    req_date=Column(DateTime(timezone=True), server_default=func.now())
    employee=relationship("Employee", back_populates="requests")

    @property
    def requester_name(self) -> str | None:
        return self.employee.name if self.employee else None

    @property
    def requester_branch(self) -> str | None:
        return self.employee.branch if self.employee else None

    @property
    def requester_role(self) -> str | None:
        return self.employee.role.value if self.employee and self.employee.role else None
