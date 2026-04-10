from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.server.database.database import get_db
from app.server.database.tenant import apply_tenant_filter
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.audit import AuditLog
from app.server.auth.service import get_current_user
from app.server.middlewares.auth import require_roles
from app.server.services.audit_service import AuditService
from app.server.models.audit import AuditLogListResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/tables", response_model=list[str])
def get_audit_table_names(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER))
):
    query = apply_tenant_filter(db.query(AuditLog.table_name), current_user, AuditLog)
    rows = query.distinct().order_by(AuditLog.table_name.asc()).all()
    return [row[0] for row in rows if row and row[0]]

@router.get("/logs", response_model=AuditLogListResponse)
def get_audit_logs(
    search: Optional[str] = None,
    table_name: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER))
):
    """
    Retrieve system audit logs with filtering and pagination.
    Requires ADMIN or MANAGER role.
    """
    return AuditService.get_logs(
        db, 
        current_user, 
        search=search,
        table_name=table_name,
        page=page,
        per_page=per_page
    )
