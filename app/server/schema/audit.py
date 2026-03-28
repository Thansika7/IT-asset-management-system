import uuid
from sqlalchemy import Column, DateTime, String, JSON, Text
from sqlalchemy.sql import func
from app.server.database.database import Base

class AuditLog(Base):
    __tablename__="audit_logs"
    audit_id=Column(String(50), primary_key=True, index=True, default=lambda: f"AUD-{uuid.uuid4().hex[:8].upper()}")
    table_name=Column(String(100), nullable=False)
    record_id=Column(String(50), nullable=False)
    action=Column(String(50), nullable=False)
    old_values=Column(JSON, nullable=True)
    new_values=Column(JSON, nullable=True)
    changed_by=Column(String(50), nullable=True)
    changed_at=Column(DateTime(timezone=True), server_default=func.now())
    user_role=Column(String(50), nullable=True)
    branch=Column(String(100), nullable=True)
    reason=Column(Text, nullable=True)
