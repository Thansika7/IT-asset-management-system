import json
import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.server.database.database import Base
from app.server.schema.employee import EmployeeRole


class OnboardingPreset(Base):
    """Named bundle of catalog asset IDs for new-hire allocation by role/branch."""

    __tablename__ = "onboarding_presets"

    preset_id = Column(String(50), primary_key=True, default=lambda: f"PRE-{uuid.uuid4().hex[:8].upper()}")
    name = Column(String(150), nullable=False)
    target_role = Column(String(32), nullable=True)
    branch = Column(String(100), nullable=True)
    asset_ids_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def get_asset_ids(self) -> list[str]:
        try:
            data = json.loads(self.asset_ids_json or "[]")
            return [str(x).strip() for x in data if str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            return []

    def set_asset_ids(self, ids: list[str]) -> None:
        cleaned = []
        seen = set()
        for x in ids:
            s = str(x).strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        self.asset_ids_json = json.dumps(cleaned)
