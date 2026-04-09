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
            reason=reason,
            organization_id=user.organization_id if user else None,
            branch_id=user.branch_id if user else None
        )
        db.add(audit)

    @staticmethod
    def get_logs(
        db: Session, 
        current_user: Employee, 
        search: Optional[str] = None,
        table_name: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> dict:
        from sqlalchemy import or_
        from app.server.models.audit import AuditLogRead
        from app.server.database.tenant import apply_tenant_filter
        
        query = apply_tenant_filter(db.query(AuditLog), current_user, AuditLog)
        
        if table_name:
            query = query.filter(AuditLog.table_name == table_name)
            
        if search:
            needle = f"%{search.strip()}%"
            query = query.filter(or_(
                AuditLog.table_name.ilike(needle),
                AuditLog.record_id.ilike(needle),
                AuditLog.action.ilike(needle),
                AuditLog.changed_by.ilike(needle),
                AuditLog.reason.ilike(needle)
            ))
            
        total = query.count()
        rows = query.order_by(AuditLog.changed_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        items = [AuditLogRead.model_validate(r) for r in rows]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page
        }
