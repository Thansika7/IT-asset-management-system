from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.server.schema.employee import EmployeeRole


class OnboardingPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    target_role: Optional[EmployeeRole] = None
    branch: Optional[str] = None
    asset_ids: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if not s:
            raise ValueError("Name must not be blank")
        return s

    @field_validator("branch")
    @classmethod
    def strip_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        s = v.strip()
        return s or None

    @field_validator("asset_ids")
    @classmethod
    def unique_ids(cls, values: List[str]) -> List[str]:
        seen = set()
        out = []
        for v in values:
            s = str(v).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out


class OnboardingPresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    preset_id: str
    name: str
    target_role: Optional[EmployeeRole] = None
    branch: Optional[str] = None
    asset_ids: List[str] = Field(default_factory=list)
    created_at: datetime
