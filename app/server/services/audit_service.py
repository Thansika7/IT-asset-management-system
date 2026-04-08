from typing import Optional, Union
from sqlalchemy.orm import Session
from app.server.schema.audit import AuditLog
from app.server.schema.employee import Employee

class AuditService:
    @staticmethod
    def log_change(
        db: Session,
        table_name: str,
        record_id: str,
        action: str,
        user: Employee,
        old_values: dict = None,
        new_values: dict = None,
        reason: str = None
    ):
        if action not in ["CREATE", "UPDATE", "DELETE"]:
            return
            
        audit=AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            changed_by=user.employee_id if user else "SYSTEM",
            user_role=user.role.value if user else "SYSTEM",
            branch=user.branch if user else "HEADQUARTERS",
            reason=reason
        )
        db.add(audit)
