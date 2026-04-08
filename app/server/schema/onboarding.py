import uuid
import json

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, TypeDecorator
from sqlalchemy.sql import func

from app.server.database.database import Base


class JSONListText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [value]
            return parsed if isinstance(parsed, list) else [parsed]
        return value


class OnboardingPreset(Base):
    __tablename__ = "onboarding_presets"

    preset_id = Column(String(50), primary_key=True, index=True, default=lambda: f"PRE-{uuid.uuid4().hex[:8].upper()}")
    organization_id = Column(String(50), ForeignKey("organizations.organization_id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(150), nullable=False)
    target_role = Column(String(50), nullable=True)
    branch = Column(String(150), nullable=True)
    asset_ids = Column("asset_ids_json", JSONListText, nullable=False, default=list)
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
