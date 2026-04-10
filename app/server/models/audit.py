from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    audit_id: str
    table_name: str
    record_id: str
    action: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    changed_by: Optional[str] = None
    changed_at: datetime
    user_role: Optional[str] = None
    branch: Optional[str] = None
    reason: Optional[str] = None

class AuditLogListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AuditLogRead]
    total: int
    page: int
    per_page: int
