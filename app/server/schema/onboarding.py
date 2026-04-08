import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, JSON
from sqlalchemy.sql import func

from app.server.database.database import Base


class OnboardingPreset(Base):
    __tablename__ = "onboarding_presets"

    preset_id = Column(String(50), primary_key=True, index=True, default=lambda: f"PRE-{uuid.uuid4().hex[:8].upper()}")
    organization_id = Column(String(50), ForeignKey("organizations.organization_id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(150), nullable=False)
    target_role = Column(String(50), nullable=True)
    branch = Column(String(150), nullable=True)
    asset_ids = Column(JSON, nullable=False, default=list)
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
