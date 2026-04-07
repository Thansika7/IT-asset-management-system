import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.sql import func

from app.server.database.database import Base


class ConfigurationItem(Base):
    """CMDB configuration item (CI)."""

    __tablename__ = "configuration_items"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)

    ci_id = Column(String(50), primary_key=True, index=True, default=lambda: f"CI-{uuid.uuid4().hex[:10].upper()}")
    ci_type = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    asset_id = Column(String(50), ForeignKey("assets.asset_id"), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CIRelationship(Base):
    __tablename__ = "ci_relationships"
    organization_id=Column(String(50), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    branch_id=Column(String(50), ForeignKey("branches.branch_id"), nullable=True, index=True)

    relationship_id = Column(String(50), primary_key=True, index=True, default=lambda: f"REL-{uuid.uuid4().hex[:10].upper()}")
    source_ci = Column(String(50), ForeignKey("configuration_items.ci_id"), nullable=False, index=True)
    target_ci = Column(String(50), ForeignKey("configuration_items.ci_id"), nullable=False, index=True)
    relationship_type = Column(String(50), nullable=False)
