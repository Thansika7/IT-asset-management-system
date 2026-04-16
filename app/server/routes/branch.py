from typing import Optional
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.database.tenant import apply_tenant_filter
from app.server.schema.employee import Employee
from app.server.schema.organization import Branch, BranchStatus


router = APIRouter(prefix="/branches", tags=["branches"])
logger = logging.getLogger(__name__)


@router.get("/")
def list_branches(
    search: Optional[str] = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    query = apply_tenant_filter(db.query(Branch), current_user, Branch)
    if active_only:
        query = query.filter(Branch.status == BranchStatus.ACTIVE)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Branch.branch_name.ilike(needle),
                Branch.location.ilike(needle),
            )
        )
    rows = query.order_by(Branch.branch_name.asc()).all()
    logger.info("Dropdown returning %s items for /branches", len(rows))
    return [
        {
            "id": row.branch_id,
            "branch_id": row.branch_id,
            "name": row.branch_name,
            "branch_name": row.branch_name,
            "location": row.location,
            "status": row.status.value if hasattr(row.status, "value") else row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]
